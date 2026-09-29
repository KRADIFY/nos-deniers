"""Targeted navigation/provenance update; source data and retrieval untouched."""
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/lexmachine-budget');BUNDLE=Path(__file__).resolve().parent
WORK=ROOT/'presentation/20260929-navigation-preuves';IMAGE='lexmachine-budget:20260929-navigation-preuves'
BASE='lexmachine-budget:20260929-style-classique-sans-audit'
ASSETS={'/assets/explorer.js':'explorer.js','/assets/explorer.css':'explorer.css','/':'explorer.html'}
FILES={'/app/public/assets/explorer.js':'explorer.js','/app/public/assets/explorer.css':'explorer.css','/app/public/explorer.html':'explorer.html','/app/budget_service/api.py':'api.py'}
def read(p):return json.loads(Path(p).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.new');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.chmod(0o644);tmp.replace(p)
def run(*args):subprocess.run([str(a) for a in args],check=True)
def output(*args):return subprocess.check_output([str(a) for a in args],text=True).strip()
def fetch(base,path):
 with urllib.request.urlopen(base+path,timeout=45) as r:return r.read()
def inventory(image):
 code="from pathlib import Path; import hashlib,json; print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app').rglob('*') if p.is_file() and '__pycache__' not in p.parts}))"
 return json.loads(output('docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',image,'python','-c',code))
def idle():
 if json.loads(fetch('http://127.0.0.1:8554','/api/status')).get('status')=='running':raise ValueError('Un audit est en cours : attendre sa fin avant la publication.')
def verify(hashes,version):
 for attempt in range(30):
  try:fetch('http://127.0.0.1:8552','/readyz');break
  except Exception:time.sleep(2)
 else:raise ValueError('Le site ne redemarre pas.')
 for url in ('http://127.0.0.1:8552','https://budget.lexmachine.net'):
  for path,h in hashes.items():
   if sha(fetch(url,path))!=h:raise ValueError('Fichier different : '+url+path)
  if b'audit-link' in fetch(url,'/'):raise ValueError('Lien public audit inattendu.')
  if json.loads(fetch(url,'/api/bootstrap'))['meta']['data_version']!=version:raise ValueError('Version des donnees differente.')
def restore(receipt):
 write(receipt['compose_path'],receipt['compose']);run('docker','compose','-f',receipt['compose_path'],'up','-d','--no-deps','web')
 verify(receipt['hashes'],receipt['data_version']);write(ROOT/'deployment.json',receipt['deployment']);print('Version precedente restauree.')
def main():
 manifest=read(BUNDLE/'FILES.json')
 for name,h in manifest.items():
  p=(BUNDLE/name).resolve()
  if not p.is_relative_to(BUNDLE) or digest(p)!=h:raise ValueError('Paquet different : '+name)
 idle();deployment=read(ROOT/'deployment.json');active=deployment.get('presentation',{}).get('image')
 if '--rollback' in sys.argv:
  if active!=IMAGE:raise ValueError('Cette version n est pas active.')
  restore(read(WORK/'rollback.json'));return
 if active==IMAGE:
  receipt=read(WORK/'rollback.json');verify({path:manifest[name] for path,name in ASSETS.items()},receipt['data_version']);print('Version deja active et verifiee.');return
 release=Path(deployment['release'])
 if release!=ROOT/'releases/20260928-controles':raise ValueError('Release inattendue, aucun changement.')
 compose=release/'compose.yaml';before=read(compose)
 if before['services']['web']['image']!=BASE:raise ValueError('Image precedente inattendue.')
 cid=output('docker','compose','-f',compose,'ps','-q','web')
 if not cid or json.loads(output('docker','inspect',cid))[0]['Config']['Image']!=BASE:raise ValueError('Conteneur inattendu.')
 previous=inventory(BASE)
 hashes={path:sha(fetch('http://127.0.0.1:8552',path)) for path in ASSETS}
 for path,name in ASSETS.items():
  imagepath=next(k for k,v in FILES.items() if v==name)
  if hashes[path]!=previous[imagepath]:raise ValueError('Fichiers actifs modifies hors image.')
 db=release/'data/derived/budget.sqlite';dbhash=digest(db)
 version=json.loads(fetch('http://127.0.0.1:8552','/api/bootstrap'))['meta']['data_version']
 receipt=dict(compose_path=str(compose),compose=before,deployment=deployment,hashes=hashes,data_version=version,database_sha256=dbhash)
 WORK.mkdir(parents=True,exist_ok=True);WORK.chmod(0o755)
 if (WORK/'rollback.json').exists():
  if read(WORK/'rollback.json')!=receipt:raise ValueError('Une autre sauvegarde existe.')
 else:write(WORK/'rollback.json',receipt)
 for name in list(manifest)+['FILES.json']:
  target=WORK/name
  if (BUNDLE/name).resolve()!=target.resolve():shutil.copyfile(BUNDLE/name,target)
  target.chmod(0o644)
 run('docker','build','--network','none','-t',IMAGE,WORK)
 current=inventory(IMAGE);changed={p for p in set(previous)|set(current) if previous.get(p)!=current.get(p)}
 if changed!=set(FILES) or any(current[p]!=manifest[name] for p,name in FILES.items()):raise ValueError('La modification depasse les quatre fichiers prevus.')
 idle()
 if read(compose)!=before or read(ROOT/'deployment.json')!=deployment:raise ValueError('Le site a change pendant la preparation.')
 config=json.loads(json.dumps(before));config['services']['web']['image']=IMAGE
 try:
  write(compose,config);run('docker','compose','-f',compose,'up','-d','--no-deps','web')
  verify({path:manifest[name] for path,name in ASSETS.items()},version)
  if digest(db)!=dbhash:raise ValueError('Base modifiee.')
  deployment['presentation'].update(image=IMAGE,css_sha256=manifest['explorer.css'],html_sha256=manifest['explorer.html'],javascript_sha256=manifest['explorer.js'],style='classique',public_audit_link=False,installed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),rollback_command='sudo python3 '+str(WORK/'install.py')+' --rollback')
  deployment['interface_update']=dict(tag='20260929-navigation-preuves',files=manifest,data_unchanged=True)
  write(ROOT/'deployment.json',deployment)
 except BaseException:
  print('Verification interrompue : retour automatique a la version precedente.');restore(receipt);raise
 print('Navigation, chargement et preuves mis a jour : https://budget.lexmachine.net/')
 print('Style classique, chiffres, index et auditeur conserves. Actualiser avec Ctrl+F5.')
if __name__=='__main__':
 try:
  if os.geteuid()!=0 or socket.gethostname()!='vmi3274092':raise ValueError('Executer avec sudo sur le VPS prevu.')
  with (ROOT/'.update.lock').open('a') as lock:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
 except Exception as e:print('Installation interrompue : '+str(e),file=sys.stderr);sys.exit(1)
