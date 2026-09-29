import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from budget_service import consultation as c

class CacheTests(unittest.TestCase):
    def test_identical_concurrent_requests_are_calculated_once(self):
        cache=c.ResponseCache(); calls=[]; barrier=threading.Barrier(12)
        def factory():
            calls.append(1);time.sleep(.12)
            return c.Payload.encode({'amount':123.45,'missing':None,'zero':0})
        def get(_): barrier.wait();return cache.get('same',factory)
        with ThreadPoolExecutor(12) as pool: results=list(pool.map(get,range(12)))
        self.assertEqual(len(calls),1)
        self.assertTrue(all(r is results[0] for r in results))
        self.assertEqual(json.loads(results[0].body),{'amount':123.45,'missing':None,'zero':0})
        self.assertEqual(cache.status()['pending'],0)

    def test_errors_never_poison_cache(self):
        cache=c.ResponseCache()
        with self.assertRaises(ValueError):cache.get('x',lambda:(_ for _ in ()).throw(ValueError()))
        self.assertEqual(cache.get('x',lambda:c.Payload.encode(42)).body,b'42')

    def test_failures_reach_waiters_then_can_retry(self):
        cache=c.ResponseCache();start=threading.Event();release=threading.Event()
        def fail():start.set();release.wait(2);raise ValueError('failed')
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(cache.get,'x',fail);start.wait(2)
            b=pool.submit(cache.get,'x',fail);time.sleep(.03);release.set()
            for f in [a,b]:
                with self.assertRaises(ValueError):f.result()
        self.assertEqual(cache.status()['pending'],0)

    def test_byte_and_entry_limits_evict_lru(self):
        cache=c.ResponseCache(max_bytes=10,max_entries=2)
        val=lambda:c.Payload(b'12345',None)
        cache.get('a',val);cache.get('b',val);cache.get('a',val);cache.get('c',val)
        self.assertEqual(list(cache.entries),['a','c']);self.assertEqual(cache.bytes,10)
        cache.get('too_big',lambda:c.Payload(b'longer than ten',None))
        self.assertNotIn('too_big',cache.entries)

    def test_compressed_response_and_plain_are_identical(self):
        p=c.Payload.encode({'text':['énergie']*500})
        self.assertEqual(gzip.decompress(p.packed),p.body)

    def test_filter_dimensions_are_distinct(self):
        base=c.query_key('/api/explorer',{})
        for q in [{'measure':['AE']},{'exclude':['["TA/345"]']},{'constant':['1']},
                  {'scope':['TA']},{'budget':['BA']},{'start':['2017']},{'base':['2017']},
                  {'topic':['maprimerenov']},{'topic_mode':['without']},{'denominator':['OUVERT']}]:
            self.assertNotEqual(base,c.query_key('/api/explorer',q))
        self.assertEqual(base,c.query_key('/api/explorer',{'measure':['CP'],'exclude':['[]']}))
        self.assertNotEqual(c.query_key('/api/provenance',{'year':['2023'],'stage':['LFI']}),
                            c.query_key('/api/provenance',{'year':['2023'],'stage':['EXEC']}))

    def test_query_parameter_order_does_not_duplicate_cache(self):
        self.assertEqual(c.query_key('/api/documents',{'q':['x'],'year':['2023']}),
                         c.query_key('/api/documents',{'year':['2023'],'q':['x']}))

    def test_background_defers_when_foreground_calculates(self):
        cache=c.ResponseCache();start=threading.Event();release=threading.Event()
        def factory():start.set();release.wait(2);return c.Payload.encode(1)
        with ThreadPoolExecutor(1) as pool:
            f=pool.submit(cache.get,'busy',factory);start.wait(2)
            with self.assertRaises(c.Busy):cache.get('other',factory,background=True)
            release.set();f.result()

    def test_cold_calculations_are_bounded(self):
        cache=c.ResponseCache(computations=2);lock=threading.Lock();active=peak=0
        def factory():
            nonlocal active,peak
            with lock:active+=1;peak=max(active,peak)
            time.sleep(.04)
            with lock:active-=1
            return c.Payload.encode(1)
        with ThreadPoolExecutor(8) as pool:list(pool.map(lambda n:cache.get(n,factory),range(8)))
        self.assertEqual(peak,2)

    def test_database_audit_and_wal_changes_invalidate(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c.api,'DATA',Path(d)):
            root=Path(d)/'derived';root.mkdir();p=root/'budget.sqlite';p.write_bytes(b'a')
            s1=c.data_stamp();p.write_bytes(b'bb');s2=c.data_stamp()
            (root/'budget.sqlite-wal').write_bytes(b'c');s3=c.data_stamp()
            (root/'data-audit.json').write_text('{}');s4=c.data_stamp()
            self.assertEqual(len({s1,s2,s3,s4}),4)

    def test_mutation_during_computation_never_cached(self):
        cache=c.ResponseCache()
        with patch.object(c,'CACHE',cache),patch.object(c,'data_stamp',side_effect=['a','b']),patch.object(c,'build',return_value=c.Payload.encode(1)):
            with self.assertRaises(c.Busy):c.response('/api/bootstrap',{})
        self.assertEqual(cache.status()['entries'],0)

    def test_new_generation_never_uses_old_response(self):
        cache=c.ResponseCache()
        with patch.object(c,'CACHE',cache),patch.object(c,'data_stamp',return_value='a'),patch.object(c,'build',return_value=c.Payload.encode(1)):
            c.response('/api/bootstrap',{})
        with patch.object(c,'CACHE',cache),patch.object(c,'data_stamp',return_value='b'),patch.object(c,'build',return_value=c.Payload.encode(2)):
            self.assertEqual(c.response('/api/bootstrap',{}).body,b'2')

    def test_warmup_repeats_search_not_a_health_probe(self):
        with patch.object(c,'response'),patch.object(c.retrieval_client,'configured',return_value=True),patch.object(c.retrieval_client,'request',return_value={'available':True}) as req,patch.object(c,'_LAST_REQUEST',0):
            a=c.keep_warm_cycle();b=c.keep_warm_cycle()
            self.assertEqual(req.call_count,2)
            self.assertIn('/search?',req.call_args.args[0]);self.assertIn('mode=hybrid',req.call_args.args[0])
            self.assertEqual(a[-1]['status'],'warm')

    def test_warmup_defers_search_for_recent_visitors(self):
        with patch.object(c,'response'),patch.object(c.retrieval_client,'configured',return_value=True),patch.object(c.retrieval_client,'request') as req,patch.object(c,'_LAST_REQUEST',time.monotonic()):
            self.assertEqual(c.keep_warm_cycle()[-1]['status'],'deferred');req.assert_not_called()

    def test_warmup_failure_not_reported_as_success(self):
        with patch.object(c,'response',side_effect=OSError()),patch.object(c.retrieval_client,'configured',return_value=False):
            self.assertTrue(all(r['status']=='failed' for r in c.keep_warm_cycle()))

    def test_stop_event_interrupts_routine(self):
        stop=threading.Event();stop.set()
        with patch.object(c,'response') as fn:
            self.assertEqual(c.keep_warm_cycle(stop),[]);fn.assert_not_called()

if __name__=='__main__':unittest.main()
