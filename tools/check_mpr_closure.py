"""HTTP/source checks on a local real-database review copy; no SQL writes."""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/mpr-closure-20260920'
RUNTIME=OUT/'runtime'
os.environ['BUDGET_DATA_DIR']=str(RUNTIME)
os.environ['BUDGET_PUBLIC_DIR']=str(ROOT/'public')
sys.path[:0]=[str(ROOT),str(RUNTIME)]
from budget_service import api, topics, data_quality


def prepare():
    # This database is an exact read-only copy of the running service's database.
    db=api.connect()
    ids={r['source'] for r in topics.registry()['facts']}
    for r in topics.registry()['timeline']:
        ids.update(c['source'] for c in r['references'])
    p=api.parameters({'topic':['maprimerenov'],'start':['2020'],'end':['2026']})
    for year in range(2020,2027):
        for stage in ('PLF','LFI','OUVERT','EXEC'):
            for measure in ('AE','CP'):
                pr=dict(p,measure=measure)
                x=data_quality.mpr(topics.subset('',year,stage,pr,{}),pr,year,stage,'')
                ids.update(r['source'] for r in x['references'])
    sources=[]
    for sid in sorted(ids):
        s=api.source(db,sid)
        target=(RUNTIME/s['path']).resolve()
        assert target.is_relative_to(RUNTIME.resolve())
        target.parent.mkdir(parents=True,exist_ok=True)
        origin=ROOT/'reports/dossiers/maprimerenov/sources'/target.name
        cached=OUT/'local-pages'/f'{sid}.json'
        if not origin.exists() and cached.exists():
            d=json.loads(cached.read_text(encoding='utf-8'))
            origin=Path(d['document']['physical_path'])
        if not target.exists():
            if origin.exists():
                shutil.copyfile(origin,target)
            else:
                with urllib.request.urlopen('http://127.0.0.1:8552/api/download/'+sid,timeout=30) as response:
                    target.write_bytes(response.read())
        content=target.read_bytes()
        assert hashlib.sha256(content).hexdigest()==s['sha256'],sid
        assert content.startswith(b'%PDF-'),sid
        sources.append(dict(id=sid,sha256=s['sha256'],bytes=len(content)))
    checks=[]
    for year in range(2020,2027):
        for stage in ('PLF','LFI','OUVERT','EXEC'):
            for measure in ('AE','CP'):
                for scope in ('','TA'):
                    for mode in ('only',):
                        pr=dict(p,start=year,end=year,measure=measure,scope=scope,topic_mode=mode)
                        proof=api.provenance(db,pr,year,stage,scope)
                        assert proof['explanation']
                        for ref in proof.get('citations',[]):
                            assert api.source(db,ref['source'])['id']==ref['source']
                        checks.append(dict(year=year,stage=stage,measure=measure,scope=scope,mode=mode,status=proof['calculation']['status']))
        print(f'Justificatifs {year} vérifiés',flush=True)
    additions=json.loads((OUT/'integration.json').read_text(encoding='utf-8'))['additions']
    for row in additions:
        year=row['year'];stage=row['stage'];measure=row['measure'];scope='TA'
        pr=dict(p,start=year,end=year,measure=measure,scope=scope,topic_mode='without')
        proof=api.provenance(db,pr,year,stage,scope)
        if proof['calculation']['base_nominal'] is None:
            assert proof['calculation']['result_nominal'] is None
            assert proof['explanation']['title']=='Total de départ nécessaire au retrait'
        else:
            assert proof['calculation']['subtracted_nominal']==row['cents']/100,(year,stage,measure)
        checks.append(dict(year=year,stage=stage,measure=measure,scope=scope,mode='without',status=proof['calculation']['status']))
    original=json.loads((OUT/'before/maprimerenov.json').read_text(encoding='utf-8'))
    assert all(r in topics.registry()['facts'] for r in original['facts'])
    result=dict(success=True,checked_sources=sources,provenance_checks=len(checks),checks=checks,
                sql_facts=db.execute('SELECT count(*) FROM facts').fetchone()[0],
                old_topic_facts_preserved=len(original['facts']),new_topic_facts=17)
    (OUT/'source-and-provenance-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(sources)} PDF vérifiés par empreinte ; {len(checks)} justificatifs contrôlés ; {result["sql_facts"]} faits SQL.',flush=True)


if __name__=='__main__':
    if '--serve' in sys.argv:
        from budget_service.web import Handler, ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        url=f'http://127.0.0.1:{server.server_address[1]}'
        (OUT/'preview-url.txt').write_text(url,encoding='utf-8')
        print('Aperçu de contrôle : '+url,flush=True)
        server.serve_forever()
    else:
        prepare()
