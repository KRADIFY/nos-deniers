"""Check the MPR calculation against documentary amounts, then freeze API evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/mpr-exclusion-20260910'
OLD=ROOT/'deploy/update-20260910-actions-chronologie'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def get(base,path):
    with urllib.request.urlopen(base+path,timeout=60) as r:return json.load(r)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--http',default='http://127.0.0.1:8552')
    parser.add_argument('--unit-tests',type=int,required=True)
    a=parser.parse_args()
    base=a.http.rstrip('/')
    spec=importlib.util.spec_from_file_location('previous_verify',OLD/'verify.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    previous=json.loads((OLD/'release.json').read_text(encoding='utf-8'))
    for case in previous['cases']:
        assert v.signature(get(base,'/api/explorer?'+case['query']))==case['expected'],case['name']
    receipt=json.loads((REPORT/'frontend-validation.json').read_text(encoding='utf-8'))
    assert receipt['passed'] and receipt['source_sha256']==sha(ROOT/'public/assets/explorer.js')
    version=sha(ROOT/'budget_service/data/maprimerenov.json')
    cases=[]
    def explorer(name,**params):
        route='/api/explorer?'+urllib.parse.urlencode(params)
        d=get(base,route);assert d['topic_version']==version
        cases.append(dict(name=name,kind='explorer',route=route,expected=dict(v.signature(d),topic_version=version)))
        return d
    def provenance(name,**params):
        route='/api/provenance?'+urllib.parse.urlencode(params)
        d=get(base,route)
        cases.append(dict(name=name,kind='provenance',route=route,expected={k:d[k] for k in ('calculation','evidence','citations')}))
        # Every cited source must be available in the downloadable catalogue.
        assert {c['source'] for c in d['citations']} <= {s['id'] for s in d['sources']}
        return d
    nominal={}
    for measure in ('AE','CP'):
        q=dict(start=2017,end=2025,scope='TA',measure=measure,budget='BG',
               exclude=json.dumps(['TA/345','TA/235']),topic='maprimerenov',topic_mode='without')
        d=explorer('ecologie-three-exclusions-'+measure,**q)
        assert all(r['EXEC']['status']=='ok' for r in d['totals'])
        expected2020=1389267838704 if measure=='AE' else 1330574538730
        expected2025=1634987523810 if measure=='AE' else 1603968674926
        assert d['totals'][3]['EXEC']['nominal_cents']==expected2020
        assert d['totals'][-1]['EXEC']['nominal_cents']==expected2025
        nominal[measure]=[(r['year'],r['EXEC']['nominal_cents']) for r in d['totals']]
        constant=explorer('ecologie-three-exclusions-constant-'+measure,**dict(q,constant=1,base=2017))
        assert all(r['EXEC']['nominal_cents']==s['EXEC']['nominal_cents'] for r,s in zip(d['totals'],constant['totals']))
        for year in (2020,2025):
            for stage in (('LFI','EXEC') if year==2020 else ('PLF','LFI','EXEC')):
                p=provenance(f'proof-{year}-{stage}-{measure}',**dict(q,start=year,end=year,year=year,stage=stage,cell_scope='TA'))
                c=p['calculation'];assert c['status']=='ok'
                assert round(c['base_nominal']*100)-round(c['subtracted_nominal']*100)==round(c['result_nominal']*100)
                if year==2020:
                    expected=390000000 if stage=='LFI' else (575000000 if measure=='AE' else 455000000)
                    assert c['subtracted_nominal']==expected
                    assert {'source':'df8d92ccd79f7b889547','page':415} in p['citations']
                    assert any(r['operation']=='subtract' and r['cents']==-expected*100 for r in p['rows'])
                else:
                    assert c['subtracted_nominal']==0 and p['evidence']
                    assert all(e['kind']=='outside_scope' and not e['is_published_zero'] for e in p['evidence'])
                    assert not any(r['operation']=='subtract' for r in p['rows'])
                    assert all(p['sources'])
    for year in (2020,2025,2026):
        for scope in ('','VA/135'):
            d=explorer('unknown-national-or-anah-'+str(year)+'-'+(scope or 'all'),start=year,end=year,scope=scope,topic='maprimerenov',topic_mode='only',measure='CP')
            assert d['totals'][0]['EXEC']['value'] is None
    p=provenance('national2025-incomplete-with-documentary-proof',start=2025,end=2025,year=2025,stage='EXEC',cell_scope='',scope='',topic='maprimerenov',topic_mode='only',measure='CP')
    assert p['calculation']['result_nominal'] is None and p['evidence']
    p=provenance('ecology2025-derived-perimeter-only',start=2025,end=2025,year=2025,stage='EXEC',cell_scope='TA',scope='TA',topic='maprimerenov',topic_mode='only',measure='CP')
    assert p['count']==0 and p['evidence'] and p['calculation']['result_nominal']==0
    # Read and hash the actual public PDF bytes used for the new proof.
    documents=[json.loads((REPORT/'mpr-2020.json').read_text(encoding='utf-8'))['source']]
    documents+=json.loads((REPORT/'perimetre-2025.json').read_text(encoding='utf-8'))['sources']
    verified=[]
    for doc in documents:
        with urllib.request.urlopen(base+'/api/download/'+doc['id'],timeout=60) as response:
            content=response.read()
        assert content.startswith(b'%PDF-') and hashlib.sha256(content).hexdigest()==doc['sha256'],doc['id']
        verified.append(dict(id=doc['id'],sha256=doc['sha256'],bytes=len(content)))
    report=dict(passed=True,unit_tests=a.unit_tests,predecessor_release_sha256=sha(OLD/'release.json'),
                topic_version=version,previous_case_changes=[],previous_cases_passed=len(previous['cases']),
                mpr_evidence_cases=cases,frontend_validation=receipt,execution_cents=nominal,verified_source_pdfs=verified)
    (REPORT/'release-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,previous_cases=len(previous['cases']),new_cases=len(cases),source_pdfs=len(verified)),ensure_ascii=False))
if __name__=='__main__':main()

