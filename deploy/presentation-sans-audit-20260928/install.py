"""Install the selected CSS and remove the public audit link only."""
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/lexmachine-budget');BUNDLE=Path(__file__).resolve().parent
WORK=ROOT/'presentation/20260928-css-sans-audit';IMAGE='lexmachine-budget:20260928-presentation-sans-audit'
BASE='lexmachine-budget:20260928-controles';CSS='/app/public/assets/explorer.css'
OLD_CSS='b71052fa78d46c3e85a099a6abb1853b1860e69cd571c85c7f091bd19da1703c'

def read(p):return json.loads(Path(p).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):
    p=Path(p);tmp=p.with_name(p.name+'.new');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.chmod(0o644);tmp.replace(p)
def run(*args):subprocess.run([str(a) for a in args],check=True)
def output(*args):return subprocess.check_output([str(a) for a in args],text=True).strip()
def fetch(base,path):
    with urllib.request.urlopen(base+path,timeout=30) as r:return r.read()
def idle():
    if json.loads(fetch('http://127.0.0.1:8554','/api/status')).get('status')=='running':
        raise ValueError('Un audit est en cours. Attendre sa fin et relancer cette meme commande.')
def pause_audit_if_requested():
    status=json.loads(fetch('http://127.0.0.1:8554','/api/status'))
    if status.get('status')!='running':return
    if '--pause-audit' not in sys.argv:raise ValueError('Audit en cours. Relancer avec --pause-audit pour l interrompre en conservant ses checkpoints.')
    rid=status['run_id']
    cid=output('docker','compose','-f','/opt/nos-deniers-audit/compose.json','ps','-q','audit')
    if not cid:raise ValueError('Conteneur audit introuvable.')
    code="import os,signal,sys; from pathlib import Path; rid=sys.argv[1]; found=[]\nfor p in Path('/proc').iterdir():\n if p.name.isdigit():\n  try: args=(p/'cmdline').read_bytes().split(bytes([0]))\n  except OSError: continue\n  if b'/app/worker.py' in args and rid.encode() in args:found.append(int(p.name))\nif len(found)!=1:raise RuntimeError('Processus audit non identifie sans ambiguite')\nos.kill(found[0],signal.SIGINT)"
    run('docker','exec','--user','10001:10001',cid,'python','-c',code,rid)
    for attempt in range(30):
        time.sleep(1)
        if json.loads(fetch('http://127.0.0.1:8554','/api/status')).get('status')!='running':
            print('Audit interrompu proprement. Resultats et checkpoints conserves.');return
    raise ValueError('Audit encore actif. Aucun changement au site effectue.')

def inventory(image):
    code="from pathlib import Path; import hashlib,json; print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/app').rglob('*') if p.is_file() and '__pycache__' not in p.parts}))"
    return json.loads(output('docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',image,'python','-c',code))
def verify(csshash,baseline,htmlhash=None):
    for attempt in range(30):
        try:
            fetch('http://127.0.0.1:8552','/readyz');break
        except Exception:time.sleep(2)
    else:raise ValueError('Le site ne redemarre pas.')
    for url in ('http://127.0.0.1:8552','https://budget.lexmachine.net'):
        if sha(fetch(url,'/assets/explorer.css?presentation=20260928'))!=csshash:raise ValueError('CSS different : '+url)
        for path in ('/','/assets/explorer.js'):
            if sha(fetch(url,path))!=(htmlhash if path=='/' and htmlhash else baseline[path]):raise ValueError('Contenu inattendu : '+url+path)
        if json.loads(fetch(url,'/api/bootstrap'))['meta']['data_version']!=baseline['data_version']:raise ValueError('Version de donnees differente')
def restore(receipt):
    write(receipt['compose_path'],receipt['compose'])
    run('docker','compose','-f',receipt['compose_path'],'up','-d','--no-deps','web')
    verify(receipt['css_sha256'],receipt['baseline'])
    write(ROOT/'deployment.json',receipt['deployment'])
    print('Presentation precedente restauree. Donnees conservees.')
def main():
    manifest=read(BUNDLE/'FILES.json')
    for name,h in manifest.items():
        p=(BUNDLE/name).resolve()
        if not p.is_relative_to(BUNDLE) or digest(p)!=h:raise ValueError('Fichier de livraison different : '+name)
    pause_audit_if_requested();idle();deployment=read(ROOT/'deployment.json')
    if '--rollback' in sys.argv:
        if deployment.get('presentation',{}).get('image')!=IMAGE:raise ValueError('Cette presentation n est pas active. Aucun retour arriere applique.')
        restore(read(WORK/'rollback.json'));return
    if deployment.get('presentation',{}).get('image')==IMAGE:
        verify(manifest['explorer.css'],read(WORK/'rollback.json')['baseline'],manifest['explorer.html']);print('Presentation deja publiee et verifiee.');return
    release=Path(deployment['release'])
    if release!=ROOT/'releases/20260928-controles':raise ValueError('Version du site inattendue. Aucun service modifie.')
    compose=release/'compose.yaml';before=read(compose)
    base=before['services']['web']['image']
    if base not in (BASE,'lexmachine-budget:20260928-presentation'):raise ValueError('Image precedente inattendue.')
    cid=output('docker','compose','-f',compose,'ps','-q','web')
    if not cid or json.loads(output('docker','inspect',cid))[0]['Config']['Image']!=base:raise ValueError('Conteneur actif inattendu.')
    css_before=sha(fetch('http://127.0.0.1:8552','/assets/explorer.css'))
    if css_before not in (OLD_CSS,manifest['explorer.css']):raise ValueError('CSS actuel different.')
    if sha(fetch('http://127.0.0.1:8552','/'))!='e6c64100c624f9d2a8be2c1ab78bf8e9b3c83e05d0e27f81ab60a637af6c622b':raise ValueError('Page actuelle differente de la version prevue.')
    db=release/'data/derived/budget.sqlite';dbhash=digest(db)
    baseline={p:sha(fetch('http://127.0.0.1:8552',p)) for p in ('/','/assets/explorer.js')}
    baseline['data_version']=json.loads(fetch('http://127.0.0.1:8552','/api/bootstrap'))['meta']['data_version']
    receipt=dict(compose_path=str(compose),compose=before,deployment=deployment,baseline=baseline,database_sha256=dbhash,css_sha256=css_before)
    WORK.mkdir(parents=True,exist_ok=True);WORK.chmod(0o755)
    if (WORK/'rollback.json').exists():
        old=read(WORK/'rollback.json')
        if old['compose']!=before or old['baseline']!=baseline:raise ValueError('Une autre sauvegarde existe. Aucun ecrasement.')
    else:write(WORK/'rollback.json',receipt)
    for name in list(manifest)+['FILES.json']:
        target=WORK/name
        if (BUNDLE/name).resolve()!=target.resolve():shutil.copyfile(BUNDLE/name,target)
        target.chmod(0o644)
    run('docker','build','--network','none','--build-arg','BASE='+base,'-t',IMAGE,WORK)
    previous=inventory(base);current=inventory(IMAGE)
    changed={p for p in set(previous)|set(current) if previous.get(p)!=current.get(p)}
    if changed- {CSS,'/app/public/explorer.html'} or current[CSS]!=manifest['explorer.css'] or current['/app/public/explorer.html']!=manifest['explorer.html']:raise ValueError('La mise a jour doit changer uniquement la presentation et le lien audit.')
    config=json.loads(json.dumps(before));config['services']['web']['image']=IMAGE
    idle()
    if read(compose)!=before or read(ROOT/'deployment.json')!=deployment:raise ValueError('Le site a change pendant la preparation.')
    try:
        write(compose,config)
        run('docker','compose','-f',compose,'up','-d','--no-deps','web')
        verify(manifest['explorer.css'],baseline,manifest['explorer.html'])
        if digest(db)!=dbhash:raise ValueError('Empreinte de la base differente.')
        deployment['presentation']=dict(image=IMAGE,css_sha256=manifest['explorer.css'],html_sha256=manifest['explorer.html'],public_audit_link=False,installed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),rollback_command='sudo python3 '+str(WORK/'install.py')+' --rollback')
        write(ROOT/'deployment.json',deployment)
    except BaseException:
        print('Verification interrompue : restauration automatique de la presentation precedente.');restore(receipt);raise
    print('Nouvelle presentation publiee et verifiee : https://budget.lexmachine.net/')
    print('Nouveau CSS et bouton audit retire. Chiffres, calculs, recherche et acces direct a l auditeur conserves.')
    print('Si necessaire, actualiser le navigateur avec Ctrl+F5.')
if __name__=='__main__':
    try:
        if os.geteuid()!=0 or socket.gethostname()!='vmi3274092':raise ValueError('Executer avec sudo sur le VPS prevu.')
        with (ROOT/'.update.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
    except Exception as e:print('Installation interrompue : '+str(e),file=sys.stderr);sys.exit(1)
