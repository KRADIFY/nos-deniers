"""Prepare a separate documentary addendum; never mutate an index or facts database."""
from pathlib import Path
import hashlib, json, sqlite3, subprocess, sys, re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'consolidation-vectorisation-20260924'
CONTROL = OUT / '_controle'
BASE = Path('D:/LexMachine/NosDeniers/search_20260919')
PREVIOUS = ROOT / 'retrieval-supplement-20260923-expanded'
DESKTOP = Path('C:/Users/Jean-Christophe/Desktop/Nouveau dossier')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def inventory():
    CONTROL.mkdir(parents=True,exist_ok=True)
    indexes=[]; indexed={}
    for name,folder in [('principal',BASE),('complement_actif',PREVIOUS)]:
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        c=sqlite3.connect((folder/'search.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        c.row_factory=sqlite3.Row
        cited={r[0] for r in c.execute('select distinct document_id from citations')}
        docs=[dict(r) for r in c.execute('select * from documents order by id')];c.close()
        for d in docs:
            d['has_passages']=d['id'] in cited
            if d['has_passages']: indexed.setdefault(d['source_sha256'],[]).append(dict(index=name,**d))
        indexes.append(dict(name=name,path=str(folder),manifest_sha256=sha(folder/'manifest.json'),manifest=manifest,documents=docs))
    save(CONTROL/'indexes-avant.json',indexes)
    code="import sqlite3,json; c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True); print(json.dumps({'sources':[json.loads(r[0]) for r in c.execute('select data from sources')],'facts':c.execute('select count(*) from facts').fetchone()[0]},ensure_ascii=False))"
    run=subprocess.run(['docker','exec','lexmachine-budget-web-1','python','-c',code],capture_output=True,check=True)
    active=json.loads(run.stdout)
    save(CONTROL/'sources-site-avant.json',active)
    manifest=json.loads((ROOT/'reports/MANIFEST-COLLECTE.json').read_text(encoding='utf-8-sig'))
    metadata={}
    for s in manifest+active['sources']:
        if s.get('sha256'): metadata.setdefault(s['sha256'],[]).append(s)
    files=[]
    roots=[p for p in (ROOT/'reports').iterdir() if p.is_dir() and re.search(r'202609(19|20|21|22|23|24)',p.name)]
    skip_parts=('word-qa','render','preview','test-copy','added-data','staging')
    for root in roots:
        for p in root.rglob('*'):
            if not p.is_file() or p.suffix.lower() not in ('.pdf','.html','.htm','.xls','.xlsx','.doc','.docx','.zip'):continue
            rel=p.relative_to(root)
            if any(any(tag in part.lower() for tag in skip_parts) for part in rel.parts[:-1]):continue
            if '.blocked.' in p.name or p.name in ('report.pdf','P3542023-credits.html') or 'selenium-catalogue' in p.name:continue
            files.append(p)
    files.extend(p for p in DESKTOP.iterdir() if p.is_file())
    grouped={}
    for p in sorted(set(files)):
        sig=p.read_bytes()[:1024]
        if p.suffix.lower()=='.pdf' and b'%PDF-' not in sig:continue
        if p.suffix.lower()=='.xls' and not sig.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):continue
        if p.suffix.lower() in ('.html','.htm') and p.stat().st_size<3000:continue
        identity=sha(p)
        e=grouped.setdefault(identity,dict(sha256=identity,bytes=p.stat().st_size,paths=[],indexed=indexed.get(identity,[]),metadata=metadata.get(identity,[])))
        e['paths'].append(str(p))
    missing=[]
    for identity,records in metadata.items():
        if identity not in indexed and identity not in grouped:
            missing.append(dict(sha256=identity,metadata=records))
    result=dict(indexed_documents=sum(sum(d['has_passages'] for d in i['documents']) for i in indexes),indexed_unique_sha256=len(indexed),candidates=list(grouped.values()),site_not_seen_locally=missing)
    save(CONTROL/'inventaire-initial.json',result)
    print(json.dumps(dict(indexed_documents=result['indexed_documents'],candidates=len(grouped),not_indexed=sum(not e['indexed'] for e in grouped.values()),site_not_seen_locally=len(missing))))
    for e in grouped.values():
        if not e['indexed']:print(e['sha256'][:12],e['bytes'],e['paths'][0])
    print('SITE ABSENT LOCAL')
    for e in missing:print(e['sha256'][:12],json.dumps(e['metadata'][0],ensure_ascii=False)[:550])

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    inventory()
