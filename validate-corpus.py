"""Read-only audit of the Docker budget corpus, streamed without duplicating raw files."""
import subprocess,tarfile,hashlib,json,io,logging,collections
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/".runtime"/"python-libs"))
from datetime import datetime,timezone
from pypdf import PdfReader
logging.getLogger('pypdf').setLevel(logging.ERROR)
DOCKER=r'C:\Users\Jean-Christophe\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
BASE=[DOCKER,'run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','-v','lexmachine-budget_budget_data:/data:ro','lexmachine-budget:0.1']
manifest=json.loads(subprocess.check_output(BASE+['cat','/data/metadata/manifest.json']))
expected={r['path']:r for r in manifest if r['status']=='downloaded'}
prior_path=Path(__file__).parent/'reports'/'VALIDATION-CORPUS.json'
prior=json.loads(prior_path.read_text(encoding='utf-8')) if prior_path.exists() else {}
cache={r['path']:r for r in prior.get('files',[]) if r.get('readable') is True}
results=[];seen=set()
p=subprocess.Popen(BASE+['tar','-C','/data','-cf','-','.'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
with tarfile.open(fileobj=p.stdout,mode='r|') as archive:
 for member in archive:
  path=member.name.removeprefix('./')
  if not member.isfile() or path not in expected:continue
  seen.add(path);e=expected[path];f=archive.extractfile(member);h=hashlib.sha256();chunks=[]
  kind=e.get('kind','pdf' if path.endswith('.pdf') else '')
  keep=kind in ('pdf','xls','xlsx') and member.size<=128*1024**2
  for b in iter(lambda:f.read(1024*1024),b''):
   h.update(b)
   if keep:chunks.append(b)
  r={'path':path,'kind':kind,'role':e.get('role'),'years':e.get('years_title',[]),'title':e.get('title',e.get('dataset_title')),'bytes':member.size,'sha256':h.hexdigest(),'hash_match':h.hexdigest()==e['sha256'],'size_match':member.size==e['bytes']}
  cached=cache.get(path)
  if keep and cached and cached['sha256']==r['sha256']:
   for key in ('readable','pages','first_pages_text','first_pages_have_text','classified_role','sheets'):
    if key in cached:r[key]=cached[key]
   r['parser_check_reused']=True
  elif keep:
   data=b''.join(chunks)
   try:
    if kind=='pdf':
     reader=PdfReader(io.BytesIO(data));n=len(reader.pages);text='\n'.join((reader.pages[i].extract_text() or '') for i in range(min(2,n)))
     r.update(readable=True,pages=n,first_pages_text=text[:4000],first_pages_have_text=bool(text.strip()))
     low=text.lower()
     if e.get('role')=='annexe_plf_a_classifier':
      if 'projet annuel de performances' in low or 'projets annuels de performances' in low:r['classified_role']='pap_mission'
      elif 'politique transversale' in low:r['classified_role']='document_politique_transversale'
      else:r['classified_role']='annexe_plf'
    elif kind=='xlsx' or data.startswith(b'PK'):
     import openpyxl
     w=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
     r.update(readable=True,sheets=w.sheetnames);w.close()
    else:
     import xlrd
     w=xlrd.open_workbook(file_contents=data,on_demand=True);r.update(readable=True,sheets=w.sheet_names());w.release_resources()
   except Exception as exc:r.update(readable=False,error=type(exc).__name__,error_detail=str(exc)[:160])
  results.append(r)
  if len(results)%100==0:print(json.dumps({'validated':len(results),'expected':len(expected)}),flush=True)
err=p.stderr.read().decode(errors='replace');code=p.wait()
groups=collections.defaultdict(list)
for r in results:groups[r['sha256']].append(r['path'])
summary={'at':datetime.now(timezone.utc).isoformat(),'expected_files':len(expected),'checked_files':len(results),'missing':sorted(set(expected)-seen),'hash_mismatches':sum(not r['hash_match'] for r in results),'size_mismatches':sum(not r['size_match'] for r in results),'unreadable_documents':sum(r.get('readable') is False for r in results),'pdf_files':sum(r['kind']=='pdf' for r in results),'pdf_pages':sum(r.get('pages',0) for r in results),'duplicate_groups':[v for v in groups.values() if len(v)>1],'tar_exit':code,'tar_error':err[:500]}
report=Path(__file__).parent/'reports'/'VALIDATION-CORPUS.json';report.write_text(json.dumps({'summary':summary,'files':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='duplicate_groups'},ensure_ascii=False),flush=True)
print('duplicate_groups',len(summary['duplicate_groups']),flush=True)
