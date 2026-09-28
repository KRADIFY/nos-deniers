"""Offline/HTTP checks for the cumulative reviewed-workbook and annex update."""
import argparse
import collections
import hashlib
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--http')
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    contract = json.loads((bundle / 'release.json').read_text('utf-8'))
    plan = json.loads((bundle / 'plan.json').read_text('utf-8'))
    key = lambda r: (r['year'], r['stage'], r['measure'], r['budget'], r.get('path') or r['mission'] + '/' + r['program'])
    expected = {key(r): r for r in plan['facts']}
    assert len(expected) == len(plan['facts']) == contract['added_facts']
    if args.http:
        def get(path):
            with urllib.request.urlopen(args.http.rstrip('/') + path, timeout=120) as response:
                return response.read()
        meta = json.loads(get('/api/bootstrap'))['meta']
        assert meta['data_version'] == contract['data_version'] and meta['fact_count'] == contract['fact_count']
        for route, name in [('/', 'app/public/explorer.html'), ('/assets/explorer.css', 'app/public/assets/explorer.css'), ('/assets/explorer.js', 'app/public/assets/explorer.js')]:
            assert hashlib.sha256(get(route)).hexdigest() == contract['files'][name]
        chosen = [next(r for r in plan['reviews'] if r['status'] == s) for s in ('verified', 'not_applicable', 'pending')]
        chosen += [next(r for r in plan['reviews'] if r['budget'] == b and r['status'] == 'verified') for b in ('BG', 'BA', 'CAS', 'CCF')]
        chosen += [next(r for r in plan['reviews'] if r.get('batch') == 'annexes-2017-2022-20260928' and r['stage'] == s and r['status'] == 'verified')
                   for s in ('OUVERT', 'FDC', 'REPORT_ENTRANT', 'REGLEMENT')]
        chosen += [next(r for r in plan['reviews'] if r.get('batch') == 'annexes-2017-2022-20260928' and r['status'] == 'pending')]
        for r in chosen:
            query = urllib.parse.urlencode(dict(start=r['year'], end=r['year'], measure=r['measure'], budget=r['budget'], scope=r['path']))
            cell = json.loads(get('/api/explorer?' + query))['totals'][0][r['stage']]
            if r['status'] == 'verified':
                assert cell['nominal_cents'] == expected[key(r)]['cents']
            else:
                assert cell['value'] is None
        for sid in contract['annex_sources']:
            assert hashlib.sha256(get('/api/download/' + sid)).hexdigest() == plan['verified_sources'][sid]['sha256']
        checked = len(chosen)
    else:
        # Works in the deployment container and from the permanent local project.
        if Path('/app/budget_service').exists():
            sys.path.insert(0, '/app')
        from budget_service import api
        assert digest(api.DATA / 'derived/budget.sqlite') == contract['database_sha256']
        db = api.connect()
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        meta = api.metadata(db)
        assert meta['data_version'] == contract['data_version'] and meta['fact_count'] == contract['fact_count']
        assert db.execute('select count(*) from cell_reviews').fetchone()[0] == len(plan['reviews'])
        cache = {}
        # Keep one group in memory; every review is still checked.
        for r in sorted(plan['reviews'], key=lambda item: (item['year'], item['measure'], item['budget'])):
            k = r['year'], r['measure'], r['budget']
            if k not in cache:
                cache.clear()
                p = api.parameters({a: [str(b)] for a, b in dict(start=k[0], end=k[0], measure=k[1], budget=k[2]).items()})
                records = api.selected_records(db, p)
                groups = collections.defaultdict(list)
                for row in records:
                    groups[row['mission'] + '/' + row['program'], row['stage']].append(row)
                cache[k] = p, records, groups
            p, records, groups = cache[k]
            review = records.cell_reviews[key(r)]
            assert review == r
            c = api.cell(groups[r['path'], r['stage']], r['path'], r['year'], r['stage'], p, {}, reviews={key(r): review})
            if r['status'] == 'verified':
                assert c['nominal_cents'] == expected[key(r)]['cents']
            else:
                assert c['value'] is None and c['status'] == ('missing' if r['status'] == 'pending' else 'not_applicable')
        for sid, r in plan['verified_sources'].items():
            assert digest(api.DATA / r['path']) == r['sha256'], sid
        checked = len(plan['reviews'])
        db.close()
    for measure in ('AE','CP'):
        for stage in ('LFI','OUVERT'):
            if args.http:
                q=urllib.parse.urlencode(dict(start=2024,end=2024,measure=measure,budget='BG',scope='PR/362',topic='maprimerenov'))
                c=json.loads(get('/api/explorer?'+q))['totals'][0][stage]
            else:
                from budget_service import topics
                c=topics.subset('PR/362',2024,stage,dict(budget='BG',measure=measure,exclude=[],constant=False,base=2025),{})
            if measure=='AE':assert c['value'] is None
            else:
                assert c['nominal_cents']==0 and c['approximate']
                assert dict(source='296835325a7d511d6a5a',page=48) in c['citations']
    print(json.dumps(dict(passed=True, mode='HTTP' if args.http else 'offline', checked=checked,
                         release=contract['release'], facts=contract['fact_count'],
                         scope='Contrôle du lot et de sa restitution ; les limites documentaires figurent dans le bilan indépendant.'), ensure_ascii=False))


if __name__ == '__main__':
    main()
