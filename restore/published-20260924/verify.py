"""Verify a frozen release offline or through its public HTTP API."""
import argparse
from contextlib import closing
import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NAME = '20260924-final'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def signature(data):
    return dict(data_version=data.get('data_version'), topic_version=data.get('topic_version'),
        totals=[{key: (value if key == 'year' else {field: value.get(field) for field in ('value', 'nominal_cents', 'status', 'sources')})
                 for key, value in annual.items() if key == 'year' or key in data['stages']} for annual in data['totals']])


def movement_signature(data):
    fields=('id','year','budget','mission','program','measure','kind','amount_cents','nominal_cents','value_cents','date','date_precision','source','sha256','page','status','citation')
    adjustments=[{k:r.get(k) for k in fields} for r in data.get('annual_adjustments',[])]
    adjustments.sort(key=lambda r:r['id'])
    rec_fields=('year','measure','lfi_cents','reported_net_cents','printed_net_cents','annual_adjustment_cents','annual_adjustment_ids','canonical_cents','difference_cents','status')
    recs=[{k:r.get(k) for k in rec_fields} for r in data.get('reconciliations',[])]
    recs.sort(key=lambda r:(r['year'],r['measure']))
    item_fields=('id','year','budget','mission','program','title','measure','kind','sign','amount_cents','nominal_cents','value_cents','date','date_precision','source','sha256','page','field','status','citation')
    rows=sorted(({k:r.get(k)for k in item_fields}for r in data['items']),key=lambda r:r['id'])
    return dict(annual_adjustments=adjustments,reconciliations=recs,items=rows,
                item_ids=sorted(r['id']for r in data['items']),
                dated_net_cents=sum(r['nominal_cents']for r in data['items'] if r.get('nominal_cents')is not None))


def validate_contract(manifest, certificate):
    if manifest.get('schema_version') != 2 or manifest.get('release') != NAME:
        raise ValueError('Unexpected release contract')
    counts = manifest.get('counts', {})
    if set(counts) != {'facts', 'sources', 'sql_sources', 'events'} or any(type(value) is not int or value < 1 for value in counts.values()):
        raise ValueError('Missing reviewed database counts')
    if not certificate.get('success') or certificate.get('fact_count') != counts['facts']:
        raise ValueError('Audit certificate/count mismatch')
    if certificate.get('data_signature') != manifest.get('data_signature'):
        raise ValueError('Audit certificate/database/registry signature mismatch')
    if manifest['export']['database_sha256'] != manifest['data_signature']['database_sha256']:
        raise ValueError('Database export differs from certificate')
    for name in ('cases', 'fact_checks', 'action_review_cases', 'downloads', 'retrieval_cases'):
        if not isinstance(manifest.get(name), list) or not manifest[name]:
            raise ValueError('Missing reviewed checks: ' + name)
    annual_cases=manifest.get('annual_adjustment_cases',[])
    if not isinstance(annual_cases,list) or sum(len(c['expected']['annual_adjustments'])for c in annual_cases)!=certificate.get('all_registries',{}).get('historical_annual_adjustments_checked',0):
        raise ValueError('Annual adjustment witnesses do not cover the audited count')
    base = manifest['retrieval_index']
    for key, cases in [('retrieval_supplement', 'retrieval_cases'), ('retrieval_incremental', 'retrieval_incremental_cases')]:
        extra = manifest[key]
        if base.get('state') != 'ready' or extra.get('state') != 'ready' or extra['base_input_sha256'] != base['input_sha256']:
            raise ValueError('Incompatible retrieval generations: ' + key)
        for field in ('version', 'model', 'revision', 'dimension'):
            if base[field] != extra[field]:
                raise ValueError('Incompatible retrieval ' + field)
        if len({row['source_sha256'] for row in manifest[cases]}) != extra['documents']:
            raise ValueError('Retrieval witnesses do not cover every document: ' + key)
    if any(not item.get('url', '').startswith('https://') for item in manifest['retrieval_incremental_cases']):
        raise ValueError('Incremental document without official source link')
    if len(manifest.get('disagreement_cases', [])) != len(certificate['all_registries']['action_groups_requiring_review']):
        raise ValueError('RAP disagreements lack publication witnesses')
    if len(manifest['action_review_cases']) != len(certificate['rap_actions_national_checks']['subaction_branches_requiring_review']):
        raise ValueError('Remaining blocked subaction witnesses differ')


def verify_financial(get, manifest):
    meta = get('/api/bootstrap')['meta']
    if (meta.get('fact_count'), meta.get('source_count'), meta.get('data_version')) != (
            manifest['counts']['facts'], manifest['counts']['sources'], manifest['data_version']):
        raise AssertionError('Served data/counts/version differ from frozen contract')
    audit = meta.get('reconciliation', {})
    if not audit.get('success') or audit.get('data_signature') != manifest['data_signature']:
        raise AssertionError('Served certificate does not match the financial data')
    for case in manifest['cases']:
        if signature(get(case['route'])) != case['expected']:
            raise AssertionError('Financial case: ' + case['name'])
    for case in manifest.get('annual_adjustment_cases',[]):
        if movement_signature(get(case['route']))!=case['expected']:
            raise AssertionError('Annual adjustment/RAP boundary: '+case['name'])
    for case in manifest['action_review_cases']:
        query = dict(start=case['year'], end=case['year'], measure=case['measure'], budget=case['budget'])
        def cell(scope, excluded=None):
            params = dict(query, scope=scope)
            if excluded is not None:
                params['exclude'] = json.dumps(excluded)
            result = get('/api/explorer?' + urllib.parse.urlencode(params))
            return result['totals'][0][case['stage']]
        if cell(case['parent_scope'])['nominal_cents'] != case['canonical_cents']:
            raise AssertionError('Canonical amount changed: ' + case['parent_scope'])
        for actual in (cell(case['detail_scope']), cell(case['parent_scope'], [case['detail_scope']])):
            if actual['value'] is not None or actual['status'] != 'detail_unavailable':
                raise AssertionError('Unreconciled action used automatically: ' + case['detail_scope'])
        if case.get('review_level')=='subaction':
            children=case['blocked_detail_scopes']
            for child in children:
                for actual in (cell(child),cell(case['parent_scope'],[child])):
                    if actual['value']is not None or actual['status']!='detail_unavailable':
                        raise AssertionError('Unreconciled child used: '+child)
            for actual in (cell(case['parent_scope'],children),cell(case['program_scope'],children)):
                if actual['value']is not None or actual['status']!='detail_unavailable':
                    raise AssertionError('Grouped unreconciled children bypass review: '+case['parent_scope'])
            if cell(case['program_scope'])['nominal_cents']!=case['program_canonical_cents']:
                raise AssertionError('Programme total changed: '+case['program_scope'])
            allowed=cell(case['program_scope'],[case['parent_scope']])
            if allowed['status']!='ok' or allowed['nominal_cents']!=case['allowed_parent_exclusion_cents']:
                raise AssertionError('Reviewed whole action cannot be excluded: '+case['parent_scope'])
        if case.get('cp_available'):
            query['measure'] = 'CP'
            for actual in (cell(case['detail_scope']), cell(case['parent_scope'], [case['detail_scope']])):
                if actual['value'] is None:
                    raise AssertionError('Concordant CP disabled: ' + case['detail_scope'])


    for case in manifest['disagreement_cases']:
        params = dict(start=case['year'], end=case['year'], measure=case['measure'], budget=case['budget'])
        def observed(scope, exclude=None):
            request = dict(params, scope=scope)
            if exclude is not None:
                request['exclude'] = json.dumps(exclude)
            return get('/api/explorer?' + urllib.parse.urlencode(request))['totals'][0][case['stage']]
        parent = observed(case['parent_scope'])
        action = observed(case['detail_scope'])
        remainder = observed(case['parent_scope'], [case['detail_scope']])
        if parent['nominal_cents'] != case['canonical_cents'] or parent['status'] != 'ok':
            raise AssertionError('Canonical RAP parent changed: ' + case['parent_scope'])
        if action['nominal_cents'] != case['action_cents'] or action['value'] is None:
            raise AssertionError('Reviewed RAP action hidden or changed: ' + case['detail_scope'])
        if remainder['nominal_cents'] != case['canonical_cents'] - case['action_cents']:
            raise AssertionError('RAP action exclusion does not recalculate: ' + case['detail_scope'])
        for cell in (parent, action, remainder):
            warnings = cell.get('source_disagreements') or []
            if not any(w.get('canonical_cents') == case['canonical_cents'] and
                       w.get('rap_cents') == case['rap_cents'] and
                       w.get('difference_cents') == case['difference_cents'] and
                       w.get('citations') for w in warnings):
                raise AssertionError('RAP discrepancy warning absent: ' + case['detail_scope'])


def verify_sql(db, manifest, data):
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise AssertionError('Database integrity')
    for table, key in [('facts', 'facts'), ('sources', 'sql_sources')]:
        if db.execute('SELECT count(*) FROM ' + table).fetchone()[0] != manifest['counts'][key]:
            raise AssertionError('Database count: ' + table)
    with closing(sqlite3.connect((data / 'derived/events.sqlite').as_uri() + '?mode=ro', uri=True)) as events:
        if events.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or events.execute('SELECT count(*) FROM events').fetchone()[0] != manifest['counts']['events']:
            raise AssertionError('Events database')
    allowed = {'year', 'stage', 'measure', 'budget', 'mission', 'program', 'title', 'action', 'subaction', 'category'}
    for case in manifest['fact_checks']:
        key = case['key']
        if not key or not set(key) <= allowed:
            raise ValueError('Invalid fact-check key')
        rows = db.execute('SELECT * FROM facts WHERE ' + ' AND '.join(field + '=?' for field in key), list(key.values())).fetchall()
        if len(rows) != 1 or any(dict(rows[0]).get(field) != value for field, value in case['expected'].items()):
            raise AssertionError('Exact source correction differs: ' + case['id'])


def validate_citation(cite, year, format):
    if year not in cite['years'] or cite['format'] != format:
        raise AssertionError('Year/format filter')
    if format == 'pdf':
        if not isinstance(cite.get('page'), int) or cite['page'] < 1:
            raise AssertionError('PDF physical page absent')
    elif format == 'html':
        if cite.get('page') is not None or not isinstance(cite.get('locator'), str) or not cite['locator'].strip() or cite['locator'].startswith('page:'):
            raise AssertionError('HTML must retain its real locator without a fictitious page')
    elif not cite.get('locator'):
        raise AssertionError('Source locator absent')


def verify_retrieval(get, manifest):
    indexes = [manifest[key] for key in ('retrieval_index', 'retrieval_supplement', 'retrieval_incremental')]
    base = indexes[0]
    health = get('/api/semantic-search/status')
    for field in ('passages', 'documents'):
        if health.get(field) != sum(index[field] for index in indexes):
            raise AssertionError('Retrieval count: ' + field)
    if not health.get('available') or health.get('numeric_facts_certified') is not False:
        raise AssertionError('Retrieval readiness or numeric boundary')
    for field in ('version', 'model', 'revision'):
        if health.get(field) != base[field]:
            raise AssertionError('Retrieval model: ' + field)
    for case in manifest['retrieval_cases']:
        for mode in ('text', 'hybrid'):
            format = case.get('format', 'pdf')
            params = dict(q=case['query'], year=case['year'], format=format, mode=mode, limit=10)
            result = get('/api/semantic-search?' + urllib.parse.urlencode(params))
            if not result.get('available') or not result.get('items'):
                raise AssertionError('Search absent: ' + case['source_id'] + '/' + mode)
            seen = set()
            for item in result['items']:
                first = item['citations'][0]
                key = (first['source_sha256'], first.get('page') or first.get('locator'))
                if key in seen:
                    raise AssertionError('Duplicate source page')
                seen.add(key)
                for cite in item['citations']:
                    validate_citation(cite, case['year'], format)
            found = [item for item in result['items'] if any(cite['source_sha256'] == case['source_sha256'] for cite in item['citations'])]
            if not found:
                raise AssertionError('Expected source absent: ' + case['source_id'] + '/' + mode)
            if mode == 'hybrid' and not any({'dense', 'sparse_rerank'} <= set(item['retrieval_methods']) for item in found):
                raise AssertionError('Dense/sparse source not reached')
            item = found[0]
            passage = get('/api/document-passage/' + item['id'])
            if hashlib.sha256(passage['text'].encode()).hexdigest() != passage['text_sha256'] or passage['text_sha256'] != item['text_sha256']:
                raise AssertionError('Passage text/hash mismatch')
            resolved = [cite for cite in passage['citations'] if cite['source_sha256'] == case['source_sha256'] and cite['source_id'] == case['source_id'] and cite.get('local_available')]
            if not resolved:
                raise AssertionError('Exact source resolution unavailable')
            for cite in resolved:
                validate_citation(cite, case['year'], format)


    # Every newly indexed document must resolve to its exact passage and
    # published source link. The 16 earlier local-download witnesses above
    # remain unchanged.
    for case in manifest['retrieval_incremental_cases']:
        passage = get('/api/document-passage/' + case['passage_id'])
        if passage['id'] != case['passage_id'] or hashlib.sha256(passage['text'].encode()).hexdigest() != passage['text_sha256']:
            raise AssertionError('Incremental passage text/hash differs')
        matching = [cite for cite in passage['citations'] if cite['source_sha256'] == case['source_sha256']]
        if not any(cite['url'] == case['url'] and cite['page'] == case['page'] and cite['format'] == case['format']
                   and cite['years'] == case['years'] and (cite.get('source_locator') or cite['locator']) == case['locator']
                   for cite in matching):
            raise AssertionError('Incremental document source differs: ' + case['source_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http')
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--app', type=Path, default=Path('/app'))
    parser.add_argument('--data', type=Path, default=Path('/data'))
    args = parser.parse_args()
    bundle, data = args.bundle.resolve(), args.data.resolve()
    manifest, certificate = read(bundle / 'release.json'), read(bundle / 'audit-certificate.json')
    validate_contract(manifest, certificate)
    db = None
    if args.http:
        def fetch(route):
            with urllib.request.urlopen(args.http.rstrip('/') + route, timeout=180) as response:
                return response.read()
        def get(route):
            return json.loads(fetch(route))
    else:
        sys.path.insert(0, str(args.app))
        from budget_service import api, reserves, rap_movements, events
        from budget_service.data_signature import signature as data_signature
        api.DATA = data
        db = api.connect()
        actual = data_signature(data / 'derived/budget.sqlite', args.app / 'budget_service/data')
        if actual != manifest['data_signature'] or read(data / 'derived/data-audit.json') != certificate:
            raise AssertionError('Offline database/JSON/certificate differs')
        code = read(bundle / 'image-code-manifest.json')
        if not code.get('files') or code['web_image_id'] != manifest['images']['web']['id'] or code['retrieval_image_id'] != manifest['images']['retrieval']['id'] or code['registries'] != actual['registries']:
            raise AssertionError('Code manifest registries differ')
        for item in code['files']:
            path = (args.app / item['path']).resolve()
            if not path.is_relative_to(args.app.resolve()) or digest(path) != item['sha256']:
                raise AssertionError('Image code differs: ' + item['path'])
        def get(route):
            path, _, query = route.partition('?')
            q = urllib.parse.parse_qs(query)
            p = api.parameters(q)
            if path == '/api/bootstrap': return api.bootstrap(db)
            if path == '/api/explorer': return api.explorer(db, p)
            if path == '/api/provenance': return api.provenance(db, p, int(q['year'][0]), q['stage'][0], q.get('cell_scope', [p['scope']])[0])
            if path == '/api/reserves': return reserves.query(p, api.metadata(db))
            if path == '/api/rap-movements': return rap_movements.query(db, p, api.metadata(db))
            if path == '/api/events': return events.query(data, p, api.metadata(db))
            raise ValueError('Unexpected offline route: ' + path)
    try:
        verify_financial(get, manifest)
        if db is not None:
            verify_sql(db, manifest, data)
        else:
            for route, expected in manifest['web_assets'].items():
                if hashlib.sha256(fetch(route)).hexdigest() != expected:
                    raise AssertionError('Web asset differs: ' + route)
            for source in manifest['downloads']:
                if hashlib.sha256(fetch('/api/download/' + source['id'])).hexdigest() != source['sha256']:
                    raise AssertionError('Source download differs: ' + source['id'])
            verify_retrieval(get, manifest)
            if args.http.startswith('https:'):
                for route in ('/diagnostic', '/api/status'):
                    try:
                        fetch(route)
                    except urllib.error.HTTPError as error:
                        if error.code not in (403, 404): raise
                    else:
                        raise AssertionError('Private diagnostic exposed: ' + route)
        print(json.dumps(dict(passed=True, mode='HTTP' if args.http else 'offline', release=NAME,
                              figures_and_review_boundaries=True, retrieval_checked=bool(args.http))))
    finally:
        if db is not None: db.close()


if __name__ == '__main__':
    main()
