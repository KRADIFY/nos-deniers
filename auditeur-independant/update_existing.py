"""Update the existing independent auditor only; keep reports and website untouched."""
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/nos-deniers-audit');BUNDLE=Path(__file__).resolve().parent
BUDGET=Path('/opt/lexmachine-budget')
TAG='20260928-controles';TARGET=ROOT/'releases'/TAG
COMPOSE=ROOT/'compose.json';RECEIPT=ROOT/'INSTALLED.json'

def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    p=Path(p);q=p.with_name(p.name+'.new');q.write_text(json.dumps(v,ensure_ascii=False,indent=2));q.chmod(0o644);q.replace(p)
def run(*args):subprocess.run([str(x) for x in args],check=True)
def output(*args):return subprocess.check_output([str(x) for x in args],text=True).strip()
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8554'+path,timeout=20) as r:return r.read()
def health():
    for i in range(30):
        try:
            if json.loads(get('/healthz'))['service']=='nos-deniers-audit-independant':return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError('Auditeur inaccessible')
def main():
    manifest=read(BUNDLE/'FILES.json');signature=digest(BUNDLE/'FILES.json')
    for name,expected in manifest.items():
        p=(BUNDLE/name).resolve()
        if not p.is_relative_to(BUNDLE) or digest(p)!=expected:raise ValueError('Fichier different : '+name)
    before=read(COMPOSE);receipt=read(RECEIPT)
    if json.loads(get('/api/status')).get('status')=='running':raise ValueError('Audit en cours : attendre sa fin.')
    if receipt.get('audit_update_sha256')==signature:
        health();print('Cette version est deja installee.');return
    if TARGET.exists():
        if read(TARGET/'STAGING.json')['manifest_sha256']!=signature:raise ValueError('Preparation differente : ne pas ecraser.')
    else:TARGET.mkdir(parents=True)
    TARGET.chmod(0o755)
    write(TARGET/'STAGING.json',dict(manifest_sha256=signature))
    for name in list(manifest)+['FILES.json']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BUNDLE/name,dest);dest.chmod(0o644)
    deployment=read(BUDGET/'deployment.json');site=Path(deployment['release'])
    if not site.resolve().is_relative_to((BUDGET/'releases')):raise ValueError('Site inattendu')
    db=site/'data/derived/budget.sqlite';dbhash=digest(db)
    sitecompose=site/'compose.yaml';sitehash=digest(sitecompose)
    web=output('docker','compose','-f',sitecompose,'ps','-q','web')
    if not web:raise ValueError('Site non actif')
    registries=TARGET/'reference/registries';registries.mkdir(parents=True,exist_ok=True)
    run('docker','cp',web+':/app/budget_service/data/.',registries)
    for p in TARGET.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
    image='nos-deniers-audit:'+TAG
    run('docker','build','-t',image,TARGET)
    sandbox=['docker','run','--rm','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','1536m','--cpus','1.5','--tmpfs','/tmp:size=384m,mode=1777','--shm-size','256m']
    run(*sandbox,'--mount','type=bind,source='+str(TARGET)+',target=/tests,readonly',image,'python','-m','unittest','discover','-s','/tests','-p','test_*.py','-q')
    config=json.loads(json.dumps(before));service=config['services']['audit'];service['image']=image
    found={'data':0,'registries':0}
    for i,mount in enumerate(service['volumes']):
        if mount.endswith(':/reference/data:ro'):service['volumes'][i]=str(site/'data')+':/reference/data:ro';found['data']+=1
        if mount.endswith(':/reference/registries:ro'):service['volumes'][i]=str(registries)+':/reference/registries:ro';found['registries']+=1
    if found!={'data':1,'registries':1}:raise ValueError('Montages inattendus')
    if service.get('environment',{}).get('AUDIT_QUICK_FOR_TEST'):raise ValueError('Mode rapide interdit en production')
    backup=ROOT/'backups'/('avant-'+TAG+'-'+time.strftime('%H%M%S'));backup.mkdir(parents=True)
    shutil.copy2(COMPOSE,backup/'compose.json');shutil.copy2(RECEIPT,backup/'INSTALLED.json')
    state=ROOT/'state/service-state.json'
    if state.exists():shutil.copy2(state,backup/'service-state.json')
    # Do not interrupt a run started while the image was building.
    if json.loads(get('/api/status')).get('status')=='running':raise ValueError('Nouvel audit en cours : attendre sa fin.')
    try:
        write(COMPOSE,config)
        run('docker','compose','-f',COMPOSE,'up','-d','audit');health()
        for route,name in [('/','web/index.html'),('/app.js','web/app.js'),('/memo','web/memo.html')]:
            if hashlib.sha256(get(route)).hexdigest()!=manifest[name]:raise ValueError('Interface servie differente : '+route)
        if digest(db)!=dbhash or digest(sitecompose)!=sitehash:raise ValueError('Version du site changee pendant installation')
        with urllib.request.urlopen('https://auditnosdeniers.lexmachine.net/healthz',timeout=30) as r:
            if json.load(r).get('service')!='nos-deniers-audit-independant':raise ValueError('Verification HTTPS en echec')
    except BaseException:
        write(COMPOSE,before);run('docker','compose','-f',COMPOSE,'up','-d','audit');raise
    receipt.update(audit_image=image,audit_update_sha256=signature,reference_database=str(site/'data'),data_version=deployment['data_version'],backup=str(backup),updated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),documentary_scope='Six annexes 2017-2022 ; couverture globale partielle',site_change='Aucun ; mise a jour du moteur seulement')
    write(RECEIPT,receipt)
    print('Moteur de controle mis a jour : https://auditnosdeniers.lexmachine.net/')
    print('Site, chiffres, index et anciens rapports conserves. Cliquer sur Lancer la verification pour un nouveau rapport.')
if __name__=='__main__':
    try:
        if os.geteuid()!=0 or socket.gethostname()!='vmi3274092':raise ValueError('Executer avec sudo sur le VPS prevu')
        with (ROOT/'.update.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
    except Exception as e:print('Mise a jour interrompue : '+str(e),file=sys.stderr);sys.exit(1)
