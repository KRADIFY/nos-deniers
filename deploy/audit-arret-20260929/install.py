"""Update only the auditor stop control. Preserve data, state, reports and site."""
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/nos-deniers-audit');BUNDLE=Path(__file__).resolve().parent
WORK=ROOT/'releases/20260929-arret';COMPOSE=ROOT/'compose.json';RECEIPT=ROOT/'INSTALLED.json'
BASE='nos-deniers-audit:20260928-controles';IMAGE='nos-deniers-audit:20260929-arret'
FILES={'/app/service.py':'service.py','/app/web/app.js':'web/app.js','/app/web/index.html':'web/index.html','/app/web/style.css':'web/style.css'}
ASSETS={'/':'web/index.html','/app.js':'web/app.js','/style.css':'web/style.css'}
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
 p=Path(p);tmp=p.with_name(p.name+'.new');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2));tmp.chmod(0o644);tmp.replace(p)
def run(*args):subprocess.run([str(a) for a in args],check=True)
def output(*args):return subprocess.check_output([str(a) for a in args],text=True).strip()
def get(base,path):
 with urllib.request.urlopen(base+path,timeout=20) as r:return r.read()
def inventory(image):
 code="from pathlib import Path;import hashlib,json;print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app').rglob('*') if p.is_file() and '__pycache__' not in p.parts}))"
 return json.loads(output('docker','run','--rm','--network','none','--read-only',image,'python','-c',code))
def verify(hashes):
 for i in range(30):
  try:get('http://127.0.0.1:8554','/healthz');break
  except Exception:time.sleep(1)
 else:raise ValueError('Auditeur inaccessible')
 for base in ('http://127.0.0.1:8554','https://auditnosdeniers.lexmachine.net'):
  for path,h in hashes.items():
   if hashlib.sha256(get(base,path)).hexdigest()!=h:raise ValueError('Fichier servi different : '+path)
def restore(backup):
 write(COMPOSE,backup['compose']);run('docker','compose','-f',COMPOSE,'up','-d','--no-deps','audit');verify(backup['assets']);write(RECEIPT,backup['receipt'])
def main():
 manifest=read(BUNDLE/'FILES.json')
 for name,h in manifest.items():
  path=(BUNDLE/name).resolve()
  if not path.is_relative_to(BUNDLE) or digest(path)!=h:raise ValueError('Livraison differente : '+name)
 before=read(COMPOSE);receipt=read(RECEIPT)
 if '--rollback' in sys.argv:
  if before['services']['audit']['image']!=IMAGE:raise ValueError('Cette version n est pas active.')
  restore(read(WORK/'rollback.json'));return
 if before['services']['audit']['image']==IMAGE:
  verify({k:manifest[v] for k,v in ASSETS.items()});print('Bouton arret deja installe et verifie.');return
 if before['services']['audit']['image']!=BASE:raise ValueError('Auditeur precedent inattendu.')
 cid=output('docker','compose','-f',COMPOSE,'ps','-q','audit')
 if not cid or json.loads(output('docker','inspect',cid))[0]['Config']['Image']!=BASE:raise ValueError('Conteneur auditeur inattendu.')
 backup=dict(compose=before,receipt=receipt,assets={k:hashlib.sha256(get('http://127.0.0.1:8554',k)).hexdigest() for k in ASSETS})
 WORK.mkdir(parents=True,exist_ok=True);WORK.chmod(0o755)
 if (WORK/'rollback.json').exists():
  if read(WORK/'rollback.json')!=backup:raise ValueError('Sauvegarde differente : aucun ecrasement.')
 else:write(WORK/'rollback.json',backup)
 for name in list(manifest)+['FILES.json']:
  dest=WORK/name;dest.parent.mkdir(parents=True,exist_ok=True)
  if dest.resolve()!=(BUNDLE/name).resolve():shutil.copyfile(BUNDLE/name,dest)
  dest.chmod(0o644)
 for d in WORK.rglob('*'):
  if d.is_dir():d.chmod(0o755)
 run('docker','build','--network','none','-t',IMAGE,WORK)
 old,new=inventory(BASE),inventory(IMAGE)
 if {p for p in set(old)|set(new) if old.get(p)!=new.get(p)}!=set(FILES):raise ValueError('Modification hors des quatre fichiers prevus.')
 if any(new[p]!=manifest[n] for p,n in FILES.items()):raise ValueError('Image differente du paquet.')
 run('docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp','--mount','type=bind,source='+str(WORK)+',target=/tests,readonly','-e','PYTHONPATH=/tests',IMAGE,'python','-m','unittest','discover','-s','/tests','-p','test_stop.py','-q')
 if read(COMPOSE)!=before:raise ValueError('Auditeur modifie pendant la preparation.')
 config=json.loads(json.dumps(before));config['services']['audit']['image']=IMAGE
 if json.loads(get('http://127.0.0.1:8554','/api/status')).get('status')=='running':print('Redemarrage du seul auditeur : campagne interrompue, checkpoints conserves pour reprise.')
 try:
  write(COMPOSE,config);run('docker','compose','-f',COMPOSE,'up','-d','--no-deps','audit');verify({k:manifest[v] for k,v in ASSETS.items()})
  receipt.update(audit_image=IMAGE,stop_control_sha256=digest(BUNDLE/'FILES.json'),stop_control_installed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
  write(RECEIPT,receipt)
 except BaseException:restore(backup);raise
 print('Bouton Arreter la verification installe : https://auditnosdeniers.lexmachine.net/')
 print('Site budgetaire, chiffres, index et checkpoints conserves. Actualiser avec Ctrl+F5.')
if __name__=='__main__':
 try:
  if os.geteuid()!=0 or socket.gethostname()!='vmi3274092':raise ValueError('Executer avec sudo sur le VPS prevu.')
  with (ROOT/'.update.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
 except Exception as e:print('Installation interrompue : '+str(e),file=sys.stderr);sys.exit(1)
