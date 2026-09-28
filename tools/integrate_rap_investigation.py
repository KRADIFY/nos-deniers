"""Stage documentary supplements; no active volume or existing facts are changed."""
import hashlib,json,re,shutil,sqlite3
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/recent-gaps-second-look-20260923'
OUT=ROOT/'reports/corrections-final-staging-20260923'
SOURCE=ROOT/'reports/reconciliation-10-euros-20260923/recent/budget-active-recent-staged.sqlite'

def main():
    OUT.mkdir(exist_ok=True)
    target=OUT/'budget.sqlite'
    assert not target.exists(),'Do not overwrite an existing staged database'
    with sqlite3.connect(SOURCE.resolve().as_uri()+'?mode=ro',uri=True)as src,sqlite3.connect(target)as dst:src.backup(dst)
    db=sqlite3.connect(target)
    data=json.loads((REPORT/'recent-gaps-investigation.json').read_text(encoding='utf8'))
    known={json.loads(raw)['sha256']:(sid,json.loads(raw))for sid,raw in db.execute('SELECT id,data FROM sources')}
    used={data['evidence'][e]['source']for r in data['records']for e in r['evidence_refs']}
    aliases={};sources=[];added=[]
    for alias in sorted(used):
        s=data['sources'][alias];sha=s.get('sha256');path=Path(s['path'])if s.get('path')else None
        if not sha or not path:
            aliases[alias]=dict(url=s['url'],label=alias+' · lecture officielle en ligne');continue
        assert hashlib.sha256(path.read_bytes()).hexdigest()==sha,path
        if sha in known:sid,record=known[sha]
        else:
            sid=sha[:20];assert not db.execute('SELECT 1 FROM sources WHERE id=?',(sid,)).fetchone()
            filename=sid+'-'+re.sub('[^A-Za-z0-9_.-]+','-',path.name)
            relative=Path('public/audit-20260923')/filename;destination=OUT/'added-data'/relative
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
            record=dict(id=sid,path=relative.as_posix(),sha256=sha,title=path.stem.replace('-',' '),
                url=s.get('url',''),format=path.suffix.lstrip('.').lower(),years_title=[str(s['exercise'])]if s.get('exercise')else [],
                role='documentary_evidence',status='downloaded',bytes=path.stat().st_size,pages=s.get('pages'),
                checked_at=datetime.now(timezone.utc).isoformat(),imported=False,
                provenance='Justificatif relu pour les limites RAP ; document original, empreinte contrôlée.')
            db.execute('INSERT INTO sources(id,data)VALUES(?,?)',(sid,json.dumps(record,ensure_ascii=False)))
            added.append(dict(source=record,original=str(path),staged=str(destination)))
        aliases[alias]=dict(source=sid,url=record.get('url'),label=record['title'])
        sources.append(record)
    records=[]
    nets={(r['year'],r['program']):r for r in json.loads((REPORT/'movement-net-candidates.json').read_text(encoding='utf8'))['records']}
    for old in data['records']:
        row={k:old[k]for k in ('year','budget','mission','program','kind','outcome','limitation')}
        row['references']=[];row['evidence_notes']=[]
        for eid in old['evidence_refs']:
            ev=data['evidence'][eid];ref=dict(aliases[ev['source']])
            if ev.get('page'):ref['page']=ev['page']
            if ev.get('locator'):ref['locator']=ev['locator']
            row['references'].append(ref)
            if ev.get('paraphrase'):row['evidence_notes'].append(ev['paraphrase'])
            if ev.get('blocks'):row['evidence_notes'].extend(b['text'] for b in ev['blocks'])
        if old['kind']=='movements':
            net=nets[(old['year'],old['program'])]
            row['annual_net_cents']={k.upper():v*100 for k,v in old['derived_annual_net_eur'].items()}
            row['references'] += [dict(source=net['source'],page=p['page'],label=p['label'])for p in net['proofs']]
            row['annual_summary_proofs']=net['proofs']
        records.append(row)
    public=dict(checked_at=data['date'],summary=data['summary'],records=records,sources=sources,
        scope_note='Relecture des 53 programmes-années signalés dans les RAP récents ; les compléments ne créent ni mouvement daté ni tableau de réserve estimé.')
    appfile=ROOT/'budget_service/data/rap-investigation.json'
    assert not appfile.exists(),'Preserve existing investigation registry before updating'
    appfile.write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for key,value in [('source_count',db.execute('SELECT count(*)FROM sources').fetchone()[0]),('rap_investigation',dict(checked_at=data['date'],sources_added=len(added),records=len(records))),('built_at',datetime.now(timezone.utc).isoformat())]:
        db.execute('INSERT OR REPLACE INTO meta(key,value)VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.commit();db.close()
    (OUT/'added-sources.json').write_text(json.dumps(added,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(database=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),sources_added=len(added),investigations=len(records)),ensure_ascii=False))

if __name__=='__main__':main()
