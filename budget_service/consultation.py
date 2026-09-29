"""Bounded, versioned response cache and five-minute keep-warm routine.

Only immutable public budget responses are cached. No database connection or
mutable result object is shared. Financial computation functions are unchanged.
"""
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import closing
from dataclasses import dataclass
import gzip
import json
import logging
import os
from pathlib import Path
import threading
import time
from . import api, events, reserves, rap_movements, retrieval_client

ROUTES = frozenset(('/api/bootstrap', '/api/explorer', '/api/provenance',
                    '/api/reserves', '/api/rap-movements', '/api/events', '/api/documents'))

class Busy(RuntimeError):
    pass

@dataclass(frozen=True)
class Payload:
    body: bytes
    packed: bytes | None
    disposition: str | None = None

    @property
    def size(self):
        return len(self.body) + (len(self.packed) if self.packed else 0)

    @classmethod
    def encode(cls, result, disposition=None):
        body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
        packed = gzip.compress(body, compresslevel=3, mtime=0) if len(body) >= 1024 else None
        return cls(body, packed if packed and len(packed) < len(body) else None, disposition)

class ResponseCache:
    def __init__(self, max_bytes=64*1024*1024, max_entries=128, computations=2, wait=40):
        self.max_bytes, self.max_entries, self.wait = max_bytes, max_entries, wait
        self.lock = threading.Lock()
        self.gate = threading.BoundedSemaphore(computations)
        self.entries = OrderedDict()
        self.pending = {}
        self.bytes = self.hits = self.misses = self.joined = 0

    def get(self, key, factory, *, background=False):
        if not self.max_bytes:
            return factory()
        with self.lock:
            if key in self.entries:
                self.hits += 1
                self.entries.move_to_end(key)
                return self.entries[key]
            future = self.pending.get(key)
            if future is not None:
                if background: raise Busy('Foreground calculation in progress')
                self.joined += 1
                owner = False
            else:
                if len(self.pending) >= 24 or (background and self.pending):
                    raise Busy('Calculation queue full')
                future = Future()
                self.pending[key] = future
                self.misses += 1
                owner = True
        if not owner:
            try: return future.result(timeout=self.wait)
            except FutureTimeout as exc: raise Busy('Calculation still in progress') from exc
        acquired = False
        try:
            acquired = self.gate.acquire(timeout=0 if background else self.wait)
            if not acquired: raise Busy('Calculation capacity busy')
            value = factory()
            with self.lock:
                if value.size <= self.max_bytes:
                    while self.entries and (self.bytes + value.size > self.max_bytes or len(self.entries) >= self.max_entries):
                        _, previous = self.entries.popitem(last=False)
                        self.bytes -= previous.size
                    self.entries[key] = value
                    self.bytes += value.size
            future.set_result(value)
            return value
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            if acquired: self.gate.release()
            with self.lock: self.pending.pop(key, None)

    def status(self):
        with self.lock:
            return dict(entries=len(self.entries), bytes=self.bytes, limit_bytes=self.max_bytes,
                        hits=self.hits, misses=self.misses, joined=self.joined, pending=len(self.pending))

CACHE = ResponseCache(max_bytes=max(0, int(os.environ.get('BUDGET_RESPONSE_CACHE_MIB', '64')))*1024*1024)
_LAST_REQUEST = 0.0
_STOP = threading.Event()
_THREAD = None
_WARM_LOCK = threading.Lock()
_WARM_STATE = dict(state='not_started', interval_seconds=300, completed_cycles=0)

def note_request():
    global _LAST_REQUEST
    _LAST_REQUEST = time.monotonic()

def data_stamp():
    # Published volumes are read-only. Include WAL and missing-file states so a
    # new release or administrative data replacement can never reuse an old key.
    root = api.DATA.resolve() / 'derived'
    paths = {root/name for name in ('budget.sqlite', 'budget.sqlite-wal', 'events.sqlite',
                                   'events.sqlite-wal', 'data-audit.json')}
    result = []
    for p in sorted(paths):
        try:
            s = p.stat()
            result.append((str(p), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
        except FileNotFoundError: result.append((str(p), None))
    return tuple(result)

def query_key(path, query):
    if path in ('/api/explorer', '/api/provenance'):
        p = api.parameters(query)
        if path == '/api/provenance':
            p.update(year=int(query.get('year', ['0'])[0]), stage=query.get('stage', [''])[0],
                     cell_scope=query.get('cell_scope', [p['scope']])[0])
    elif path == '/api/bootstrap': p = {}
    else: p = query
    return path, json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def build(path, query):
    disposition = None
    with closing(api.connect()) as db:
        if path == '/api/bootstrap': result = api.bootstrap(db)
        elif path == '/api/explorer': result = api.explorer(db, api.parameters(query))
        elif path == '/api/provenance':
            p = api.parameters(query)
            result = api.provenance(db, p, int(query.get('year', ['0'])[0]),
                                   query.get('stage', [''])[0], query.get('cell_scope', [p['scope']])[0])
        elif path == '/api/documents': result = api.documents(db, query)
        elif path == '/api/reserves':
            result = reserves.query(api.parameters(query), api.metadata(db))
            if query.get('download'): disposition = 'attachment; filename=nos-deniers-reserves.json'
        elif path == '/api/events':
            result = events.query(api.DATA, api.parameters(query), api.metadata(db))
            if query.get('download'): disposition = 'attachment; filename=nos-deniers-evenements.json'
        elif path == '/api/rap-movements':
            summary = query.get('view') == ['summary'] and not query.get('download')
            offset, limit = int(query.get('offset', ['0'])[0]), int(query.get('limit', ['500'])[0])
            if summary and (offset < 0 or not 1 <= limit <= 500): raise ValueError('Invalid movement page')
            result = rap_movements.query(db, api.parameters(query), api.metadata(db), include_evidence=not summary)
            if summary: result = rap_movements.page_result(result, offset, limit)
            if query.get('download'): disposition = 'attachment; filename=nos-deniers-mouvements-rap.json'
        else: raise ValueError('Uncached route')
    return Payload.encode(result, disposition)

def response(path, query, *, background=False):
    stamp = data_stamp()
    key = stamp, query_key(path, query)
    def produce():
        value = build(path, query)
        if data_stamp() != stamp: raise Busy('Data changed during calculation')
        return value
    return CACHE.get(key, produce, background=background)

def warm_targets():
    yield '/api/bootstrap', {}
    for measure in ('CP', 'AE'):
        for extra in ({}, {'scope': ['TA']}, {'topic': ['maprimerenov']}):
            yield '/api/explorer', dict(measure=[measure], **extra)
    yield '/api/documents', {'format': ['pdf']}
    yield '/api/reserves', {'scope': ['TA']}
    yield '/api/rap-movements', {'scope': ['TA'], 'view': ['summary']}

def keep_warm_cycle(stop=_STOP):
    results = []
    for path, query in warm_targets():
        if stop.is_set(): break
        try:
            response(path, query, background=True)
            results.append(dict(path=path, status='warm'))
        except Busy: results.append(dict(path=path, status='deferred'))
        except Exception as exc:
            logging.warning('Budget warmup %s failed: %s', path, type(exc).__name__)
            results.append(dict(path=path, status='failed', error=type(exc).__name__))
        if stop.wait(0.1): break
    # One real hybrid query touches FTS, dense and sparse in ALL configured
    # collections. It is never cached here; the private service owns its indexes.
    # Avoid spending search capacity while visitors are actively using the site.
    if not stop.is_set() and retrieval_client.configured():
        if time.monotonic() - _LAST_REQUEST < 60:
            results.append(dict(path='retrieval', status='deferred'))
        else:
            r = retrieval_client.request('/search?q=renovation+energetique&mode=hybrid&limit=1')
            results.append(dict(path='retrieval', status='warm' if r.get('available') else 'failed'))
    return results

def _loop(interval):
    while not _STOP.is_set():
        with _WARM_LOCK: _WARM_STATE.update(state='warming')
        try:
            results = keep_warm_cycle()
            with _WARM_LOCK:
                _WARM_STATE.update(state='warm' if all(r['status']=='warm' for r in results) else 'partial',
                                   last_cycle=time.time(), results=results,
                                   completed_cycles=_WARM_STATE['completed_cycles']+1)
        except Exception:
            logging.exception('Budget keep-warm cycle failed; retry next cycle')
            with _WARM_LOCK: _WARM_STATE.update(state='retry_pending')
        if _STOP.wait(interval): break

def start():
    global _THREAD
    if os.environ.get('BUDGET_KEEP_WARM', '1') == '0': return
    with _WARM_LOCK:
        if _THREAD is not None and _THREAD.is_alive(): return
        interval = max(60, int(os.environ.get('BUDGET_KEEP_WARM_SECONDS', '300')))
        _WARM_STATE['interval_seconds'] = interval
        _THREAD = threading.Thread(target=_loop, args=(interval,), name='budget-keep-warm', daemon=True)
        _THREAD.start()

def status():
    with _WARM_LOCK: warm = dict(_WARM_STATE)
    return dict(cache=CACHE.status(), keep_warm=warm)
