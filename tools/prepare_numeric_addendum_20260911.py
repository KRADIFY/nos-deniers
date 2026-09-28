"""Freeze a read-only numeric addendum; never import into the active preparation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
PREP = Path('D:/LexMachine/NosDeniers/preparation_20260909')
CATALOGUE = PREP / 'checkpoints/after_isolated_merge_20260911_094736.sqlite'
SITE = ROOT / 'reports/restore-20260910-actions-mpr/data/derived'
RELEASE = ROOT / 'deploy/update-20260910-reactivation/release.json'
OUTPUT = ROOT / 'reports/audit-vectorisation-20260911/numeric-addendum'
ACTION_NAMES = ('actions-p174.json', 'actions-ecologie.json', 'actions-multititres.json',
                'actions-sousactions.json', 'actions-dette.json')
REGISTRY_NAMES = ACTION_NAMES + ('maprimerenov.json', 'mouvements-rap-p174.json',
                                'reserves-ecologie.json', 'reserves-p174.json')


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write('\n')


def connect(path):
    # Only sealed snapshots are opened. Immutable avoids creating WAL/SHM files.
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def require(condition, message):
    if not condition:
        raise ValueError(message)


def walk(value, pointer=''):
    if isinstance(value, dict):
        yield pointer, value
        for key, child in value.items():
            yield from walk(child, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, pointer + '/' + str(index))


def record(path, base):
    return {'path': path.relative_to(base).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def build(out):
    require(not out.exists(), 'Output already exists: preserve the previous bundle; use --verify.')
    release = read_json(RELEASE)
    active_path = PREP / 'structured/active_stores.json'
    active = read_json(active_path)
    baseline = PREP / active['budget']['path']
    candidate = SITE / 'budget.sqlite'
    require(sha(baseline) == active['budget']['sha256'], 'Preparation numeric baseline hash changed.')
    release_files = {item['path']: item for item in release['reused_data_files']}
    for name in ('budget.sqlite', 'events.sqlite', 'normalization-report.json', 'data-audit.json'):
        meta = release_files['derived/' + name]
        require((SITE/name).stat().st_size == meta['bytes'] and sha(SITE/name) == meta['sha256'],
                'Site release snapshot mismatch: ' + name)
    require(sha(SITE/'events.sqlite') == active['events']['sha256'], 'Event registry unexpectedly changed.')

    old, new = connect(baseline), connect(candidate)
    try:
        for db in (old, new):
            require(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'Numeric integrity check failed.')
            require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'Numeric foreign-key failure.')
        columns = [row[1] for row in old.execute('PRAGMA table_info(facts)')]
        require(columns == [row[1] for row in new.execute('PRAGMA table_info(facts)')], 'Facts schema changed.')
        before = Counter(tuple(row) for row in old.execute('SELECT * FROM facts'))
        after = Counter(tuple(row) for row in new.execute('SELECT * FROM facts'))
        removed, added = before-after, after-before
        require(not removed and sum(before.values()) == 119746 and sum(after.values()) == 120576,
                'Unexpected numeric baseline or loss.')
        groups = Counter()
        for row, number in added.items():
            groups['/'.join(map(str, row[:3]))] += number
        require(groups == {'2023/FDC_PREVU/AE':415, '2023/FDC_PREVU/CP':415}, 'Unexpected numeric delta.')
        sources = {row['id']: json.loads(row['data']) for row in new.execute('SELECT id,data FROM sources')}
        numeric_ids = {row[0] for row in new.execute('SELECT DISTINCT source FROM facts')}
        added_sources = sorted({row[columns.index('source')] for row in added})
    finally:
        old.close()
        new.close()

    raw = {name: (ROOT/'budget_service/data'/name).read_bytes() for name in REGISTRY_NAMES}
    regs = {name: json.loads(content) for name, content in raw.items()}
    require(hashlib.sha256(raw['maprimerenov.json']).hexdigest() == release['topic_version'], 'Topic version changed.')
    require(hashlib.sha256(raw['mouvements-rap-p174.json']).hexdigest() == release['rap_movement_version'],
            'RAP movements version changed.')
    require(hashlib.sha256(b'\0'.join(raw[name] for name in ACTION_NAMES)).hexdigest() == release['action_detail_version'],
            'Action-detail version changed.')
    require(regs['reserves-ecologie.json']['version'] == release['reserve_version'], 'Reserve version changed.')

    # Inline topic/reserve source descriptions can add documentary references absent from facts.
    for registry in regs.values():
        for _, item in walk(registry):
            if re.fullmatch(r'[0-9a-f]{20}', str(item.get('id', ''))) and item.get('sha256'):
                previous = sources.get(item['id'])
                require(not previous or previous.get('sha256') == item['sha256'], 'Conflicting inline source hash.')
                sources[item['id']] = {**(previous or {}), **item}

    db = connect(CATALOGUE)
    try:
        assets = {row['sha256']: dict(row) for row in db.execute('SELECT * FROM assets')}
        indexed = {row['asset_sha256']: row['shard_sha256'] for row in db.execute('SELECT * FROM indexed')}
        existing_map = {row['source_id']: dict(row) for row in db.execute("SELECT * FROM numeric_source_map WHERE store='budget'")}
    finally:
        db.close()

    links, registry_audit, all_refs = {}, [], []

    def source_link(source_id):
        if source_id in links:
            return links[source_id]
        meta = sources.get(source_id)
        require(meta is not None, 'Unresolved source ID: ' + source_id)
        source_sha = meta.get('sha256') or meta.get('source_sha256')
        asset = assets.get(source_sha)
        link = {'source_id': source_id, 'source_sha256': source_sha, 'metadata': meta,
                'catalogue_asset_present': asset is not None,
                'already_indexed': source_sha in indexed,
                'extraction_shard_sha256': indexed.get(source_sha),
                'existing_numeric_mapping': source_id in existing_map,
                'preparation_source_path': asset.get('path') if asset else None,
                'public_document_url': meta.get('url'),
                'site_source_url': 'https://budget.lexmachine.net/api/source/' + source_id,
                'verification': 'SHA identity resolved against sealed preparation catalogue; no duplicate PDF copied'}
        links[source_id] = link
        return link

    for source_id in sorted(numeric_ids):
        link = source_link(source_id)
        require(link['catalogue_asset_present'] and link['already_indexed'], 'Annual fact source missing from preparation.')

    for name, registry in regs.items():
        refs = []
        dimensions = {key: set() for key in ('year', 'stage', 'measure', 'program', 'mission')}
        for pointer, item in walk(registry):
            for key in dimensions:
                if isinstance(item.get(key), (str, int)):
                    dimensions[key].add(str(item[key]))
            for key in ('source', 'source_id', 'canonical_source'):
                source_id = item.get(key)
                if not isinstance(source_id, str) or not re.fullmatch(r'[0-9a-f]{20}', source_id):
                    continue
                link = source_link(source_id)
                expected_sha = item.get('source_sha256') or item.get('sha256') if key != 'canonical_source' else None
                require(not expected_sha or expected_sha == link['source_sha256'],
                        'Registry source hash disagreement: ' + name + pointer)
                ref = {'registry': name, 'pointer': pointer, 'source_field': key, 'source_id': source_id,
                       'source_sha256': link['source_sha256'],
                       'locator': {k:item[k] for k in ('page', 'line', 'field', 'total_page') if k in item}}
                refs.append(ref)
        all_refs.extend(refs)
        digest = hashlib.sha256(raw[name]).hexdigest()
        registry_audit.append({'registry': name, 'sha256': digest, 'bytes': len(raw[name]),
            'updated_at': registry.get('updated_at'), 'version': registry.get('version'),
            'present_as_identical_catalogue_asset': digest in assets,
            'section_counts': {key:len(value) for key, value in registry.items() if isinstance(value, list)},
            'dimensions': {key:sorted(value) for key, value in dimensions.items()},
            'coverage': registry.get('coverage'), 'scope': registry.get('scope'),
            'perimeter': registry.get('perimeter'), 'limits': registry.get('limits', registry.get('limitations')),
            'method': registry.get('method', registry.get('note')), 'reference_count':len(refs),
            'source_ids': sorted({ref['source_id'] for ref in refs}),
            'role': 'sidecar_registry_not_additive_to_annual_facts',
            'embedding_policy': 'Do not embed duplicate CSV/PDF; optionally serialize reviewed explanations as a separately versioned documentary source.'})

    missing_sources = [link['source_id'] for link in links.values() if not link['catalogue_asset_present']]
    not_indexed = [link['source_id'] for link in links.values() if not link['already_indexed']]
    require(not missing_sources, 'Registry source assets missing: ' + str(missing_sources))
    for source_id in added_sources:
        require(source_link(source_id)['already_indexed'], 'Added fact source needs indexing unexpectedly.')

    # All checks above are read-only. Writes below create this new handoff directory only.
    out.mkdir(parents=True)
    target_db = out/'structured'/('budget_' + sha(candidate) + '.sqlite')
    target_db.parent.mkdir()
    shutil.copyfile(candidate, target_db)
    require(sha(target_db) == sha(candidate), 'Copied numeric snapshot mismatch.')
    (out/'registries').mkdir()
    for name in REGISTRY_NAMES:
        (out/'registries'/name).write_bytes(raw[name])
    (out/'support').mkdir()
    for name in ('normalization-report.json', 'data-audit.json'):
        shutil.copyfile(SITE/name, out/'support'/name)
    write_json(out/'support/preparation-active-stores-before.json', active)
    write_json(out/'support/release-versions.json', {key:release[key] for key in
               ('release', 'data_version', 'reserve_version', 'action_detail_version', 'topic_version', 'rap_movement_version')})
    write_json(out/'numeric-comparison.json', {'passed':True, 'facts_columns':columns,
        'previous_facts':119746, 'current_facts':120576, 'unchanged_previous_facts':119746,
        'removed_or_modified_previous_rows':0, 'added_facts':830, 'added_by_year_stage_measure':dict(groups),
        'added_source_ids':added_sources, 'unit':'cents', 'NULL_preserved':True,
        'comparison':'complete multiset comparison of every facts column; both snapshots quick_check=ok',
        'previous_sha256':sha(baseline), 'current_sha256':sha(target_db), 'new_csv_embeddings_needed':0})
    write_json(out/'source-links.json', {'sources':sorted(links.values(), key=lambda x:x['source_id']),
        'registry_occurrences':all_refs, 'missing_asset_source_ids':missing_sources,
        'not_indexed_source_ids':not_indexed, 'pdf_files_copied':0})
    write_json(out/'registry-audit.json', {'registries':registry_audit,
        'warning':'Year/stage/measure dimensions are observed keys, not a claim that every combination is covered.',
        'overlaps':['reserves-p174 is a subset of reserves-ecologie; do not union-add them',
                    'action parents repeat canonical programme totals; detail substitutes, it is not added',
                    'MaPrimeRenov shares programme credits and is a scoped subtraction, not additional spending',
                    'RAP movements describe annual credits; do not add them again to annual opened/consumed figures']})
    map_rows = [{'store':'budget', 'source_id':source_id,
                 'asset_sha256':source_link(source_id)['source_sha256'],
                 'metadata_json':json.dumps(sources[source_id], ensure_ascii=False, sort_keys=True)}
                for source_id in sorted(numeric_ids)]
    write_json(out/'import-plan.json', {'state':'prepared_not_imported', 'requires_exclusive_preparation_lock':True,
        'gpu_launch_authorized':False, 'run_only_after_OCR_writer_and_finalizer_stop':True,
        'expected_previous_budget':active['budget'],
        'new_budget':{'bundle_path':target_db.relative_to(out).as_posix(),
                      'destination':'structured/versions/'+target_db.name,'sha256':sha(target_db),'records':120576},
        'events_unchanged':active['events'], 'budget_numeric_source_map_upserts':map_rows,
        'steps':[
            'Verify every manifest file hash; acquire the preparation lock and verify the actual active stores and catalogue generation.',
            'Create a verified coherent backup; recheck all numeric source asset hashes against the current catalogue.',
            'Copy the new budget snapshot under its versioned destination; do not concatenate it with older snapshots.',
            'Transactionally upsert the budget numeric_source_map rows supplied here; keep event mappings separate.',
            'Register sidecar JSON files in a separate versioned registry manifest, preserving scope, unit, precision, NULLs and provenance; do not append their parent/detail values to facts.',
            'Atomically point active_stores budget to the new snapshot; preserve events and historical snapshots.',
            'Update a separate addendum receipt/current budget count to 120576; preserve the historical complement receipt at119746 and update report readers to resolve the latest version instead of reapplying the old complement.',
            'Recompute final readiness and frozen handoff manifest with active numeric SHA, registry SHAs and current catalogue generation; keep GPU gate closed until document/table reviews pass.',
            'Test one added FDC_PREVU fact per AE/CP, one preserved NULL, and references from MPR/actions/reserves/movements; validate all old annual rows are unchanged.',
            'The CSV source is already indexed: no duplicate document embedding or wholesale re-embedding is required for this numeric addendum.'
        ]})
    files = [record(path, out) for path in sorted(out.rglob('*')) if path.is_file()]
    write_json(out/'manifest.json', {'schema':'nos-deniers-numeric-addendum-v1',
        'created_at':datetime.now(timezone.utc).isoformat(), 'status':'ready_for_controlled_import_not_imported',
        'release':'20260910-reactivation', 'release_manifest_sha256':sha(RELEASE),
        'catalogue_snapshot':str(CATALOGUE),
        'catalogue_snapshot_receipt':read_json(Path(str(CATALOGUE)+'.receipt.json')),
        'builder_sha256':sha(Path(__file__)), 'files':files,
        'summary':{'previous_facts':119746, 'current_facts':120576, 'added':830, 'removed':0,
                   'registries':len(registry_audit), 'source_links':len(links),
                   'not_indexed_source_ids':not_indexed, 'new_csv_embeddings_needed':0, 'pdf_files_copied':0}})
    verify(out)


def verify(out):
    manifest = read_json(out/'manifest.json')
    for item in manifest['files']:
        path = (out/item['path']).resolve()
        require(path.is_relative_to(out.resolve()), 'Unsafe manifest path.')
        require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'Bundle file mismatch: '+item['path'])
    report = read_json(out/'numeric-comparison.json')
    require(report['passed'] and report['added_facts'] == 830 and report['removed_or_modified_previous_rows'] == 0,
            'Invalid comparison receipt.')
    plan = read_json(out/'import-plan.json')
    db = connect(out/plan['new_budget']['bundle_path'])
    try:
        require(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'Copied database integrity failed.')
        require(db.execute('SELECT count(*) FROM facts').fetchone()[0] == 120576, 'Copied database count failed.')
    finally:
        db.close()
    print(json.dumps({'passed':True, 'bundle':str(out),'manifest_sha256':sha(out/'manifest.json'),
                      **manifest['summary']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    verify(args.output) if args.verify else build(args.output)
