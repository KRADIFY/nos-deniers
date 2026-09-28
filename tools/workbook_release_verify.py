"""Runtime verification shipped with the bounded workbook update."""
import argparse,hashlib,json,sqlite3,sys,urllib.request
from pathlib import Path

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--http');args=parser.parse_args()
    bundle=Path(__file__).resolve().parent
    contract=json.loads((bundle/'release.json').read_text());plan=json.loads((bundle/'plan.json').read_text())
    if args.http:
        def get(path):return urllib.request.urlopen(args.http.rstrip('/')+path,timeout=60).read()
        meta=json.loads(get('/api/bootstrap'))['meta']
        assert meta['data_version']==contract['data_version'] and meta['fact_count']==123483
        for route,name in [('/','app/public/explorer.html'),('/assets/explorer.css','app/public/assets/explorer.css'),('/assets/explorer.js','app/public/assets/explorer.js')]:
            assert hashlib.sha256(get(route)).hexdigest()==contract['files'][name],route
        selected=[next(r for r in plan['reviews'] if r['status']==s) for s in ('verified','not_applicable','pending')]
        selected += [next(r for r in plan['reviews'] if r['budget']==b and r['status']=='verified') for b in ('BG','BA','CAS','CCF')]
        from urllib.parse import urlencode
        for r in selected:
            q=urlencode(dict(start=r['year'],end=r['year'],measure=r['measure'],budget=r['budget'],scope=r['path']))
            c=json.loads(get('/api/explorer?'+q))['totals'][0][r['stage']]
            if r['status']=='verified':
                f=next(f for f in plan['facts'] if (f['year'],f['stage'],f['measure'],f['budget'],f['mission']+'/'+f['program'])==(r['year'],r['stage'],r['measure'],r['budget'],r['path']))
                assert c['nominal_cents']==f['cents']
            else: assert c['value'] is None
    else:
        sys.path.insert(0,'/app')
        from budget_service import api
        assert digest(api.DATA/'derived/budget.sqlite')==contract['database_sha256']
        db=api.connect();assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        meta=api.metadata(db);assert meta['data_version']==contract['data_version'] and meta['fact_count']==123483
        assert db.execute('select count(*) from cell_reviews').fetchone()[0]==648
        cache={}
        for r in plan['reviews']:
            k=(r['year'],r['measure'],r['budget'])
            if k not in cache:
                p=api.parameters({a:[str(b)] for a,b in dict(start=k[0],end=k[0],measure=k[1],budget=k[2]).items()})
                cache[k]=p,api.selected_records(db,p)
            p,records=cache[k]
            c=api.cell(records,r['path'],r['year'],r['stage'],p,{},reviews=records.cell_reviews)
            if r['status']=='verified':
                f=next(f for f in plan['facts'] if (f['year'],f['stage'],f['measure'],f['budget'],f['mission']+'/'+f['program'])==(r['year'],r['stage'],r['measure'],r['budget'],r['path']))
                assert c['nominal_cents']==f['cents']
            else: assert c['value'] is None and c['status']==('missing' if r['status']=='pending' else 'not_applicable')
        for sid,r in plan['verified_sources'].items():assert digest(api.DATA/r['path'])==r['sha256'],sid
        db.close()
    print(json.dumps(dict(passed=True,mode='HTTP' if args.http else 'offline',release=contract['release'],data_version=contract['data_version'])))
if __name__=='__main__':main()
