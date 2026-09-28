"""Integrate the sealed numeric addendum into an explicitly supplied catalogue COPY.

No CLI automatically applies this operation, no active preparation is modified, and
no GPU work is started. Consumers may activate a generation only after its final
numeric_addendum_receipt.json is present and verified.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


REGISTRIES = ('actions-p174.json', 'actions-ecologie.json', 'actions-multititres.json',
              'actions-sousactions.json', 'actions-dette.json', 'maprimerenov.json',
              'mouvements-rap-p174.json', 'reserves-ecologie.json', 'reserves-p174.json')
STAMP = 'numeric_addendum_20260911'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n'


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _child(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    _require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe relative path')
    target = (root/relative).resolve()
    _require(target.is_relative_to(root) and target != root, 'Path escapes generation')
    return target


def _ro(path):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con


def _copy_verified(source, target, expected):
    _require(_sha(source) == expected, 'Source hash mismatch: '+str(source))
    if target.exists():
        _require(_sha(target) == expected, 'Existing generation file differs: '+str(target))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name+'.partial')
    with Path(source).open('rb') as source_stream, partial.open('wb') as output_stream:
        shutil.copyfileobj(source_stream, output_stream)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    _require(_sha(partial) == expected, 'Copy hash mismatch')
    os.replace(partial, target)


def _write(path, value):
    encoded = _json(value).encode('utf-8')
    if path.exists() and path.read_bytes() == encoded:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name+'.partial')
    with partial.open('wb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path)


def _numeric_comparison(before_path, after_path):
    before_db, after_db = _ro(before_path), _ro(after_path)
    try:
        for db in (before_db, after_db):
            _require(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'Numeric SQLite integrity failed')
        columns = [row[1] for row in before_db.execute('PRAGMA table_info(facts)')]
        _require(columns == [row[1] for row in after_db.execute('PRAGMA table_info(facts)')], 'Fact schema differs')
        _require(columns[:3] == ['year', 'stage', 'measure'], 'Unexpected budget dimensions')
        before = Counter(tuple(row) for row in before_db.execute('SELECT * FROM facts'))
        after = Counter(tuple(row) for row in after_db.execute('SELECT * FROM facts'))
        _require(sum(before.values()) == 119746 and sum(after.values()) == 120576, 'Unexpected numeric generation counts')
        _require(not before-after, 'Old annual observations lost or modified')
        delta = Counter()
        for row, number in (after-before).items():
            delta['/'.join(map(str, row[:3]))] += number
        _require(delta == {'2023/FDC_PREVU/AE':415, '2023/FDC_PREVU/CP':415}, 'Unexpected numeric delta')
        return {'before':119746, 'after':120576, 'added':830, 'removed_or_modified':0,
                'delta':dict(delta), 'comparison':'complete multiset of all facts columns'}
    finally:
        before_db.close()
        after_db.close()


def integrate_numeric_addendum(catalogue_path, generation_root, addendum_root, source_preparation_root):
    """Stage one numeric generation and transactionally update its copied catalogue.

    All four paths are explicit. The caller must have exclusive ownership of the
    copied catalogue and must not expose the generation before this returns passed.
    Source preparation paths are opened/read only; their historical receipts remain.
    A repeated call verifies and reuses identical files and SQL rows. If interrupted
    after SQL commit, it finishes the active-stores pointer and completion receipt.
    """
    root, bundle, source = map(lambda p:Path(p).resolve(),
                               (generation_root, addendum_root, source_preparation_root))
    catalogue = Path(catalogue_path).resolve()
    _require(root != source and not source.is_relative_to(root), 'Generation must not contain the active preparation')
    _require(root != bundle and not bundle.is_relative_to(root), 'Generation must not contain the sealed addendum')
    _require(catalogue.is_file() and catalogue.is_relative_to(root), 'Catalogue must be an existing copy inside the generation')
    _require(catalogue.stat().st_nlink == 1, 'Refusing a hard-linked catalogue; supply an independent copy')
    _require(catalogue != (source/'nos_deniers.sqlite').resolve(), 'Refusing the active preparation catalogue')
    # Never mistake the shared immutable reference snapshots for a disposable copy.
    _require(not catalogue.is_relative_to(source/'checkpoints'), 'Refusing a source checkpoint')
    _require(not Path(str(catalogue)+'-wal').exists() or Path(str(catalogue)+'-wal').stat().st_size == 0,
             'Copied catalogue has a non-empty WAL; supply a sealed coherent copy')

    manifest = _read(bundle/'manifest.json')
    manifest_sha = _sha(bundle/'manifest.json')
    _require(manifest.get('schema') == 'nos-deniers-numeric-addendum-v1', 'Unexpected addendum schema')
    files = {entry['path']:entry for entry in manifest['files']}
    _require(len(files) == len(manifest['files']), 'Duplicate manifest paths')
    for relative, entry in files.items():
        path = _child(bundle, relative)
        _require(path.stat().st_size == entry['bytes'] and _sha(path) == entry['sha256'], 'Addendum file mismatch: '+relative)
    plan = _read(bundle/'import-plan.json')
    source_active = _read(source/'structured/active_stores.json')
    baseline = plan['expected_previous_budget']
    incoming = plan['new_budget']
    current_sha = source_active['budget']['sha256']
    _require(current_sha in (baseline['sha256'], incoming['sha256']), 'Source numeric version is neither expected generation')
    _require(source_active['events'] == plan['events_unchanged'], 'Events registry changed outside addendum')
    before_path = _child(source, baseline['path'])
    _require(_sha(before_path) == baseline['sha256'], 'Expected baseline snapshot differs')
    after_path = _child(bundle, incoming['bundle_path'])
    _require(_sha(after_path) == incoming['sha256'], 'Incoming budget snapshot differs')
    comparison = _numeric_comparison(before_path, after_path)

    links_document = _read(bundle/'source-links.json')
    links = {entry['source_id']:entry for entry in links_document['sources']}
    _require(not links_document['missing_asset_source_ids'] and not links_document['not_indexed_source_ids'],
             'Addendum has unresolved/unindexed sources')
    mappings = plan['budget_numeric_source_map_upserts']
    _require(len(mappings) == 58 and len({row['source_id'] for row in mappings}) == 58, 'Expected 58 unique budget mappings')
    registry_audit = _read(bundle/'registry-audit.json')['registries']
    _require({item['registry'] for item in registry_audit} == set(REGISTRIES), 'Registry list differs')

    sidecar_root = 'structured/numeric_addenda/'+manifest_sha
    registry_stores = {'schema':'nos-deniers-registry-stores-v1', 'addendum_manifest_sha256':manifest_sha,
                       'aggregation':'Sidecars are not added to annual facts; preserve source-specific units and scopes.',
                       'registries':{}}
    for item in registry_audit:
        name = item['registry']
        origin = _child(bundle, 'registries/'+name)
        digest = _sha(origin)
        _require(digest == item['sha256'], 'Registry audit digest differs')
        relative = 'structured/registry_versions/'+digest+'/'+name
        registry_stores['registries'][name] = {'path':relative, 'sha256':digest, 'bytes':origin.stat().st_size,
                                             'source_release':manifest['release'], 'role':item['role']}

    active = dict(_read(bundle/'support/preparation-active-stores-before.json'))
    active['budget'] = {'path':incoming['destination'], 'sha256':incoming['sha256'], 'records':120576}
    active['previous_budget'] = baseline
    historical = active['historical_budget']
    historical_sha = _sha(_child(source, historical['path']))
    _require(not historical.get('sha256') or historical['sha256'] == historical_sha, 'Historical numeric snapshot differs')
    active['historical_budget'] = {**historical, 'sha256':historical_sha}
    registry_relative = sidecar_root+'/registry-stores.json'
    registry_sha = hashlib.sha256(_json(registry_stores).encode('utf-8')).hexdigest()
    active['registries'] = {'path':registry_relative, 'sha256':registry_sha, 'count':9}
    active['numeric_addendum'] = {'manifest_sha256':manifest_sha, 'receipt':'numeric_addendum_receipt.json'}
    active_sha = hashlib.sha256(_json(active).encode('utf-8')).hexdigest()
    pointer = _child(root, 'structured/active_stores.json')
    if pointer.exists():
        previous_pointer = _read(pointer)
        _require(previous_pointer['budget']['sha256'] in (baseline['sha256'], incoming['sha256']),
                 'Generation already points to an unrelated budget')

    stamp = {'schema':'nos-deniers-numeric-integration-v1', 'manifest_sha256':manifest_sha,
             'budget_sha256':incoming['sha256'], 'active_stores_sha256':active_sha,
             'registries_sha256':registry_sha, 'phase':'sql_committed'}
    extraction_updates = []
    con = sqlite3.connect(str(catalogue), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA foreign_keys=ON')
        _require(con.execute("SELECT 1 FROM sqlite_master WHERE name='numeric_source_map'").fetchone(), 'Catalogue lacks numeric provenance schema')
        prior = con.execute('SELECT value FROM metadata WHERE key=?', (STAMP,)).fetchone()
        _require(not prior or json.loads(prior['value']) == stamp, 'Another numeric addendum already owns this generation')
        # Validate all identities before writing any SQL or copying payloads.
        for entry in links.values():
            digest = entry['source_sha256']
            _require(con.execute('SELECT 1 FROM assets WHERE sha256=?', (digest,)).fetchone(),
                     'Source asset missing from target catalogue: '+entry['source_id'])
            ext = con.execute('SELECT shard_sha256 FROM indexed WHERE asset_sha256=?', (digest,)).fetchone()
            _require(ext, 'Source is not indexed in target catalogue: '+entry['source_id'])
            if ext['shard_sha256'] != entry['extraction_shard_sha256']:
                # OCR/table repairs may replace the derived shard without changing
                # the source PDF. Preserve its new indexed extraction, never reset it.
                extraction = con.execute("SELECT 1 FROM sqlite_master WHERE name='extraction'").fetchone()
                _require(extraction, 'Updated extraction has no verification table')
                fresh = con.execute('SELECT status,shard_sha256 FROM extraction WHERE asset_sha256=?', (digest,)).fetchone()
                _require(fresh and fresh['status'] == 'complete' and fresh['shard_sha256'] == ext['shard_sha256'],
                         'Updated extraction/index disagree for source: '+entry['source_id'])
                extraction_updates.append({'source_id':entry['source_id'], 'source_sha256':digest,
                    'previous_shard_sha256':entry['extraction_shard_sha256'], 'current_shard_sha256':ext['shard_sha256']})
        for row in mappings:
            _require(row['store'] == 'budget' and row['source_id'] in links, 'Unexpected mapping store/source')
            _require(row['asset_sha256'] == links[row['source_id']]['source_sha256'], 'Mapping disagrees with source links')
            prior_map = con.execute("SELECT asset_sha256 FROM numeric_source_map WHERE store='budget' AND source_id=?", (row['source_id'],)).fetchone()
            _require(not prior_map or prior_map['asset_sha256'] == row['asset_sha256'], 'Conflicting existing numeric source identity')

        _copy_verified(after_path, _child(root, incoming['destination']), incoming['sha256'])
        _copy_verified(before_path, _child(root, baseline['path']), baseline['sha256'])
        for key in ('events', 'historical_budget'):
            item = active[key]
            origin = _child(source, item['path'])
            digest = item.get('sha256') or _sha(origin)
            _copy_verified(origin, _child(root, item['path']), digest)
        for name, item in registry_stores['registries'].items():
            _copy_verified(_child(bundle, 'registries/'+name), _child(root, item['path']), item['sha256'])
        # Map every original addendum file into this autonomous generation. Large
        # numeric snapshots and registries reuse their versioned destination once.
        file_locations = {}
        for relative, entry in files.items():
            if relative == incoming['bundle_path']:
                destination = incoming['destination']
            elif relative.startswith('registries/') and Path(relative).name in registry_stores['registries']:
                destination = registry_stores['registries'][Path(relative).name]['path']
            else:
                destination = sidecar_root+'/bundle/'+relative
            _copy_verified(_child(bundle,relative), _child(root,destination), entry['sha256'])
            file_locations[relative] = {'generation_path':destination, 'sha256':entry['sha256'], 'bytes':entry['bytes']}
        _copy_verified(bundle/'manifest.json', _child(root,sidecar_root+'/manifest.json'), manifest_sha)
        _write(_child(root,sidecar_root+'/bundle-file-locations.json'), file_locations)
        _write(_child(root, registry_relative), registry_stores)

        con.execute('BEGIN IMMEDIATE')
        try:
            latest = con.execute('SELECT value FROM metadata WHERE key=?', (STAMP,)).fetchone()
            _require((latest['value'] if latest else None) == (prior['value'] if prior else None), 'Concurrent numeric integration detected')
            con.execute('CREATE TABLE IF NOT EXISTS numeric_registry_versions(registry_key TEXT PRIMARY KEY,relative_path TEXT NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,source_release TEXT NOT NULL,role TEXT NOT NULL,addendum_manifest_sha256 TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS numeric_registry_citations(registry_key TEXT NOT NULL,pointer TEXT NOT NULL,source_field TEXT NOT NULL,source_id TEXT NOT NULL,source_sha256 TEXT NOT NULL,locator_json TEXT NOT NULL,PRIMARY KEY(registry_key,pointer,source_field))')
            for row in mappings:
                con.execute('INSERT INTO numeric_source_map(store,source_id,asset_sha256,metadata_json) VALUES(?,?,?,?) ON CONFLICT(store,source_id) DO UPDATE SET asset_sha256=excluded.asset_sha256,metadata_json=excluded.metadata_json',
                            (row['store'], row['source_id'], row['asset_sha256'], row['metadata_json']))
            for name, item in registry_stores['registries'].items():
                old = con.execute('SELECT sha256 FROM numeric_registry_versions WHERE registry_key=?', (name,)).fetchone()
                _require(not old or old['sha256'] == item['sha256'], 'Conflicting registry version in copied catalogue')
                con.execute('INSERT INTO numeric_registry_versions VALUES(?,?,?,?,?,?,?) ON CONFLICT(registry_key) DO NOTHING',
                            (name,item['path'],item['sha256'],item['bytes'],item['source_release'],item['role'],manifest_sha))
            for item in links_document['registry_occurrences']:
                _require(item['registry'] in REGISTRIES and item['source_id'] in links, 'Unresolved registry citation')
                _require(item['source_sha256'] == links[item['source_id']]['source_sha256'], 'Registry citation SHA differs')
                row = (item['registry'],item['pointer'],item['source_field'],item['source_id'],item['source_sha256'],_json(item['locator']))
                existing = con.execute('SELECT * FROM numeric_registry_citations WHERE registry_key=? AND pointer=? AND source_field=?', row[:3]).fetchone()
                _require(not existing or tuple(existing) == row, 'Conflicting existing registry citation')
                con.execute('INSERT INTO numeric_registry_citations VALUES(?,?,?,?,?,?) ON CONFLICT(registry_key,pointer,source_field) DO NOTHING', row)
            con.execute('INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (STAMP,_json(stamp)))
            _require(con.execute('SELECT count(*) FROM numeric_registry_versions WHERE addendum_manifest_sha256=?', (manifest_sha,)).fetchone()[0] == 9,
                     'Registry integration count differs')
            for row in mappings:
                stored = con.execute('SELECT asset_sha256,metadata_json FROM numeric_source_map WHERE store=? AND source_id=?', (row['store'],row['source_id'])).fetchone()
                _require(tuple(stored) == (row['asset_sha256'],row['metadata_json']), 'Numeric mapping readback failed')
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
    finally:
        con.close()

    # Only this final pair publishes numeric readiness within the private generation.
    # The caller must wait for this receipt before publishing/using that generation.
    _write(pointer, active)
    _require(_sha(pointer) == active_sha, 'Active stores pointer readback failed')
    receipt = {'schema':'nos-deniers-numeric-integration-v1', 'passed':True,
        'state':'integrated_into_private_generation', 'manifest_sha256':manifest_sha,
        'catalogue_relative_path':catalogue.relative_to(root).as_posix(),
        'active_stores_sha256':active_sha, 'registry_manifest_sha256':registry_sha,
        'addendum_manifest_path':sidecar_root+'/manifest.json',
        'addendum_files_map_path':sidecar_root+'/bundle-file-locations.json',
        'comparison':comparison, 'budget_mappings':58, 'registries':9,
        'registry_citations':len(links_document['registry_occurrences']),
        'preserved_extraction_updates':extraction_updates,
        'new_document_embeddings':0, 'public_activation_performed':False, 'gpu_launch_performed':False,
        'historical_complement_receipt_preserved':True}
    _write(root/'numeric_addendum_receipt.json', receipt)
    return receipt
