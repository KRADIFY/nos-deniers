from pathlib import Path
import json,hashlib,shutil
R=Path(__file__).resolve().parents[1];B=R/'reports/import-supplement-20260909';X=R/'vectorisation-nos-deniers-20260909';C=X/'_controle';H=C/'export-history/avant-supplement-20260909';H.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def backup(p):
 q=H/p.name
 assert not q.exists(),q
 shutil.copy2(p,q)
p=read(B/'plan.json');receipt=read(B/'receipt.json');mp=R/'reports/MANIFEST-COLLECTE.json'
assert sha(mp)==p['base_manifest_sha256'];backup(mp);shutil.copyfile(B/'manifest-merged.json',mp)
items=[]
for row in p['new_records']:
 rel='sources-documentaires/supplement-20260909/'+Path(row['path']).name;dst=X/rel;dst.parent.mkdir(parents=True,exist_ok=True);assert not dst.exists();shutil.copy2(B/'incoming'/row['original_filename'],dst);assert sha(dst)==row['sha256']
 items.append(dict(row,export_relative_path=rel,id=hashlib.sha256(row['path'].encode()).hexdigest()[:20],years=row['years_title'],embed_document=True))
save(C/'supplement-20260909.json',dict(items=items,summary=p['summary']))
db=X/'donnees-structurees/budget.sqlite';backup(db);assert sha(B/'budget-after.sqlite')==receipt['database_sha256'];shutil.copyfile(B/'budget-after.sqlite',db)
v=C/'export-validation.json';backup(v);obj=read(v);obj['files']['donnees-structurees/budget.sqlite'].update(bytes=db.stat().st_size,sha256=sha(db));obj['catalogue_refresh']=dict(at=receipt['at'],source_count=4272,facts_unchanged=True);save(v,obj)
script=C/'export-global-verify.py';backup(script);s=script.read_text(encoding='utf-8');s=s.replace("'collecte-manuelle-20260909.json']","'collecte-manuelle-20260909.json', 'supplement-20260909.json']",1)
marker="for row in core['references']:";s=s.replace(marker,"for row in manifests['supplement-20260909.json']['items']:\n    register(dict(row, corpus='catalogue-nos-deniers', provenance_manifest='_controle/supplement-20260909.json'), row)\n\n"+marker,1);s=s.replace('global-avant-collecte-manuelle-20260909','global-avant-supplement-20260909');script.write_text(s,encoding='utf-8')
shutil.copyfile(B/'receipt.json',C/'supplement-20260909-receipt.json')
print('Exported',len(items),'new PDFs')
