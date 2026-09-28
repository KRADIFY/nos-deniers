"""Stage, audit and apply the reviewed forecast addition while preserving all facts."""
import collections,hashlib,json,os,shutil,sqlite3,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,'/app')
from budget_service import api,import_fdc_forecast as fdc
DATA=Path('/data');OUT=Path('/report');WORK=DATA/'imports/fdc-prevus-2023-20260910';STAGE=WORK/'staged'
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rows_digest(db,count):
 h=hashlib.sha256()
 for r in db.execute('select * from facts where rowid<=? order by rowid',(count,)):
  h.update(json.dumps(r,ensure_ascii=False,separators=(',',':')).encode());h.update(b'\n')
 return h.hexdigest()
def connect(p):return sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
def main():
 if '--apply' in sys.argv:
  receipt=json.loads((OUT/'staged-validation.json').read_text())
  assert receipt['all_previous_cells_preserved'] and receipt['new_facts']==830
  for f in ('budget.sqlite','normalization-report.json','data-audit.json'):
   assert digest(DATA/'derived'/f)==receipt['previous_files'][f],f
   assert digest(STAGE/'derived'/f)==receipt['staged_files'][f],f
  backup=WORK/'before';backup.mkdir(exist_ok=False)
  for f in receipt['previous_files']:shutil.copyfile(DATA/'derived'/f,backup/f)
  # Activate audited metadata first, then the coherent SQLite snapshot atomically.
  for f in ('normalization-report.json','data-audit.json','budget.sqlite'):
   part=DATA/'derived'/(f+'.fdc-2023-part');assert not part.exists()
   shutil.copyfile(STAGE/'derived'/f,part);part.chmod(0o644);part.replace(DATA/'derived'/f)
  receipt.update(state='applied_locally',applied_at=datetime.now(timezone.utc).isoformat())
  dump(OUT/'receipt.json',receipt);dump(WORK/'receipt.json',receipt)
  print('Applied 830 forecast facts; 119746 previous facts preserved.');return
 assert not STAGE.exists(),'Prepared snapshot already exists; review it before retrying.'
 OUT.mkdir(exist_ok=True);(STAGE/'derived').mkdir(parents=True)
 for p in DATA.iterdir():
  if p.name not in ('derived','imports'):(STAGE/p.name).symlink_to(p,target_is_directory=p.is_dir())
 previous_files={n:digest(DATA/'derived'/n) for n in ('budget.sqlite','normalization-report.json','data-audit.json')}
 with connect(DATA/'derived/budget.sqlite') as old:
  assert old.execute('select count(*) from facts where year=2023 and stage=?',('FDC_PREVU',)).fetchone()[0]==0
  count=old.execute('select count(*) from facts').fetchone()[0];assert count==119746
  before=rows_digest(old,count);original=list(old.execute('select * from facts'))
  record=json.loads(old.execute('select data from sources where id=?',(fdc.SOURCE_ID,)).fetchone()[0])
  added,checks=fdc.parse_source(record,original);assert len(added)==830 and len(checks)==338
  meta={k:json.loads(v) for k,v in old.execute('select * from meta')}
  with sqlite3.connect(STAGE/'derived/budget.sqlite') as new:
   old.backup(new);new.executemany('insert into facts values ('+','.join('?'*19)+')',added)
   assert rows_digest(new,count)==before
   record.update(imported=True,numeric_import=True,numeric_import_scope='Prévisions FdC/AdP du PLF 2023 uniquement, par programme et titre. Colonnes pluriannuelles 2024 et 2025 exclues.',source_precision='Euros publiés dans le fichier CSV')
   new.execute('update sources set data=? where id=?',(json.dumps(record,ensure_ascii=False),fdc.SOURCE_ID))
   now=datetime.now(timezone.utc).isoformat();meta.update(built_at=now,fact_count=count+len(added),imported_source_count=meta['imported_source_count']+1,data_version=hashlib.sha256((meta['data_version']+fdc.SOURCE_SHA+'FDC_PREVU_2023_v1').encode()).hexdigest(),stats=dict(collections.Counter(f'{r[0]}/{r[1]}/{r[3]}' for r in original+added)))
   for k,v in meta.items():new.execute('insert or replace into meta values (?,?)',(k,json.dumps(v,ensure_ascii=False)))
   new.commit();assert new.execute('pragma integrity_check').fetchone()[0]=='ok'
  dump(STAGE/'derived/normalization-report.json',meta)
 # Recompute the independent source-hash and annual total audit before activation.
 env=dict(os.environ,BUDGET_DATA_DIR=str(STAGE),BUDGET_INPUTS_DIR='/inputs')
 subprocess.run([sys.executable,'-m','budget_service.audit_data'],env=env,check=True)
 params=dict(start=2017,end=2026,budget='BG',measure='CP',scope='TA',exclude=[],constant=False,base=2017,topic='',topic_mode='only',denominator='LFI')
 api.DATA=DATA
 with api.connect() as db:previous=api.explorer(db,params)
 api.DATA=STAGE
 with api.connect() as db:updated=api.explorer(db,params)
 old_entries=[previous['totals']]+[r['series'] for r in previous['rows']]
 new_entries=[updated['totals']]+[r['series'] for r in updated['rows']]
 assert len(old_entries)==len(new_entries)
 for before_series,after_series in zip(old_entries,new_entries):
  for b,a in zip(before_series,after_series):
   for stage in previous['stages']:
    if b['year']==2023 and stage=='FDC_PREVU':continue
    assert b[stage]==a[stage],(b['year'],stage)
 total=next(r for r in updated['totals'] if r['year']==2023)['FDC_PREVU']
 assert total['nominal_cents']==277894292600 and total['status']=='ok',total
 checksums={n:digest(STAGE/'derived'/n) for n in previous_files}
 report=dict(state='staged',new_facts=830,previous_facts=count,total_facts=meta['fact_count'],programme_measure_checks=len(checks),all_previous_cells_preserved=True,source_sha256=fdc.SOURCE_SHA,data_version=meta['data_version'],previous_files=previous_files,staged_files=checksums,ecology_2023_forecast_cp_cents=277894292600,ecology_2023_forecast_ae_cents=223450706000,original_facts_sha256=before)
 dump(OUT/'staged-validation.json',report);dump(OUT/'programme-checks.json',checks);dump(OUT/'source.json',record)
 print(json.dumps(report))
if __name__=='__main__':main()