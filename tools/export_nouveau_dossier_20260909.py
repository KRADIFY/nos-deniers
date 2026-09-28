"""Archive this validated batch and refresh the existing handoff snapshot."""
from pathlib import Path
import json,hashlib,shutil,sqlite3
R=Path(__file__).resolve().parents[1];B=R/'reports/import-nouveau-dossier-20260909';X=R/'vectorisation-nos-deniers-20260909';C=X/'_controle'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def backup(p,folder):
    folder.mkdir(parents=True,exist_ok=True);q=folder/p.name
    if q.exists():assert sha(q)==sha(p),f'Existing backup differs: {q}'
    else:shutil.copy2(p,q)
p=read(B/'plan.json');receipt=read(B/'receipt.json')
assert receipt['facts_sha256']=='f8c501e07bfe2a599fee30282d8ab99ab1f9ab40f9c2e87c0492e169be621611'
assert receipt['source_count']==4253 and receipt['fact_count']==116272
manifest=R/'reports/MANIFEST-COLLECTE.json'
assert sha(manifest)==p['base_manifest_sha256']
backup(manifest,B/'before');shutil.copyfile(B/'manifest-merged.json',manifest)
items=[]
for row in p['new_records']:
    rel='sources-documentaires/collecte-manuelle-20260909/'+Path(row['path']).name
    dst=X/rel;src=Path('C:/Users/Jean-Christophe/Desktop/Nouveau dossier')/row['original_filename']
    assert sha(src)==row['sha256'];dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():shutil.copy2(src,dst)
    assert sha(dst)==row['sha256'] and dst.stat().st_size==row['bytes']
    items.append(dict(row,export_relative_path=rel,id=hashlib.sha256(row['path'].encode()).hexdigest()[:20],years=row['years_title'],embed_document=True))
save(C/'collecte-manuelle-20260909.json',dict(at=receipt['at'],summary=p['summary'],items=items))
db=X/'donnees-structurees/budget.sqlite';fresh=B/'budget-after.sqlite'
assert sha(fresh)==receipt['database_sha256']
con=sqlite3.connect(fresh.as_uri()+'?mode=ro',uri=True)
assert con.execute('pragma integrity_check').fetchone()[0]=='ok'
assert con.execute('select count(*) from sources').fetchone()[0]==4253
con.close()
history=C/'export-history/avant-collecte-manuelle-20260909'
backup(db,history);shutil.copyfile(fresh,db)
validation=C/'export-validation.json';backup(validation,history);v=read(validation)
v['files']['donnees-structurees/budget.sqlite'].update(bytes=db.stat().st_size,sha256=sha(db))
v['catalogue_refresh']=dict(at=receipt['at'],source_count=4253,facts_unchanged=True,receipt='collecte-manuelle-20260909-receipt.json')
save(validation,v);shutil.copyfile(B/'receipt.json',C/'collecte-manuelle-20260909-receipt.json')
script=C/'export-global-verify.py';backup(script,history);s=script.read_text(encoding='utf-8')
s=s.replace("'cour-textes-recuperes.json']","'cour-textes-recuperes.json', 'collecte-manuelle-20260909.json']",1)
s=s.replace('global-avant-ajout-sql-cour-20260909','global-avant-collecte-manuelle-20260909').replace('.ajout-sql-cour-new','.collecte-manuelle-new')
marker="for row in core['references']:"
addition="for row in manifests['collecte-manuelle-20260909.json']['items']:\n    register(dict(row, corpus='catalogue-nos-deniers', provenance_manifest='_controle/collecte-manuelle-20260909.json'), row)\n\n"
assert marker in s;s=s.replace(marker,addition+marker,1);script.write_text(s,encoding='utf-8')
print(json.dumps(dict(copied=len(items),catalogue_sources=4253,database_bytes=db.stat().st_size)))
