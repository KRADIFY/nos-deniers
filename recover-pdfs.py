import json,subprocess,urllib.request,hashlib,io
from pathlib import Path
from datetime import datetime,timezone
from pypdf import PdfReader
D=r'C:\Users\Jean-Christophe\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
manifest=json.loads(Path(__file__).with_name('reports').joinpath('MANIFEST-COLLECTE.json').read_text(encoding='utf-8'))
writer="""import sys,json,shutil,os
from pathlib import Path
from budget_service.collect import write_json,digest,validate
root=Path('/data');relative=Path(sys.argv[1]);p=root/relative
assert not relative.is_absolute() and '..' not in relative.parts
receipt=json.loads(sys.argv[2]);data=sys.stdin.buffer.read();assert len(data)==receipt['bytes']
temp=p.with_suffix(p.suffix+'.host-part');temp.write_bytes(data);validate(temp,'pdf');assert digest(temp)==receipt['sha256']
if p.exists():
 archived=root/'quarantine'/'before-host-repair'/relative;archived.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,archived)
temp.replace(p);write_json(p.with_suffix(p.suffix+'.receipt.json'),receipt)
print('Imported verified PDF',receipt['bytes'])
"""
for job in manifest:
 if job['status']!='failed':continue
 for attempt in range(3):
  try:
   with urllib.request.urlopen(job['url'],timeout=60) as response:
    declared=int(response.headers.get('Content-Length','0'));assert 0<declared<128*1024**2
    b=response.read(declared+1);assert len(b)==declared,(len(b),declared)
   reader=PdfReader(io.BytesIO(b));pages=len(reader.pages);assert pages>0
   receipt={k:v for k,v in job.items() if k not in ('error','attempts','duration_ms')}
   receipt.update(status='downloaded',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),pages_verified=pages,checked_at=datetime.now(timezone.utc).isoformat(),recovery_method='host_https_full_read',declared_bytes=declared)
   cmd=[D,'run','--rm','-i','--network','none','--read-only','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges:true','-v','lexmachine-budget_budget_data:/data','lexmachine-budget:0.1','python','-c',writer,job['path'],json.dumps(receipt)]
   subprocess.run(cmd,input=b,check=True)
   print(json.dumps({'title':job['title'],'pages':pages,'bytes':len(b),'status':'repaired'},ensure_ascii=False),flush=True);break
  except Exception as e:
   print(json.dumps({'title':job['title'],'attempt':attempt+1,'error':type(e).__name__,'detail':str(e)[:120]},ensure_ascii=False),flush=True)
