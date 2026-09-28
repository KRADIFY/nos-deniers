"""Install only the reviewed cells and audit button; preserve indexes and predecessor."""
import fcntl,hashlib,json,os,shutil,socket,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path('/opt/lexmachine-budget');BUNDLE=Path(__file__).resolve().parent
NEW=ROOT/'releases/20260928-classeurs';OLD=ROOT/'releases/20260924-final'
AUDIT=Path('/opt/nos-deniers-audit/compose.json')

def read(p):return json.loads(Path(p).read_text())
def write(p,data):
    p=Path(p);tmp=p.with_name(p.name+'.new');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.chmod(0o644);tmp.replace(p)
def digest(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def run(*args):subprocess.run([str(a) for a in args],check=True)
def output(*args):return subprocess.check_output([str(a) for a in args],text=True).strip()
def get(url):return json.load(urllib.request.urlopen(url,timeout=15))
def restore():
    rollback=read(NEW/'rollback.json')
    write(AUDIT,rollback['audit_compose'])
    write(Path('/opt/nos-deniers-audit/INSTALLED.json'),rollback['audit_receipt'])
    run('docker','compose','-f',OLD/'compose.yaml','up','-d','--no-deps','web')
    run('docker','compose','-f',AUDIT,'up','-d','audit')
    write(ROOT/'deployment.json',rollback['deployment'])

def install():
    contract=read(BUNDLE/'release.json');release_sha=digest(BUNDLE/'release.json')
    for rel,expected in contract['files'].items():
        p=(BUNDLE/rel).resolve()
        if not p.is_relative_to(BUNDLE) or p.is_symlink() or digest(p)!=expected:raise ValueError('Fichier de livraison différent : '+rel)
        p.chmod(0o644)
    for d in [BUNDLE]+[p for p in BUNDLE.rglob('*') if p.is_dir()]:d.chmod(0o755)
    if '--rollback' in sys.argv:restore();return
    deployment=read(ROOT/'deployment.json')
    if deployment.get('release')==str(NEW):
        if deployment.get('release_sha256')!=release_sha:raise ValueError('Autre paquet actif')
        run(sys.executable,BUNDLE/'verify.py','--http','https://budget.lexmachine.net');print('Version déjà publiée et vérifiée.');return
    if deployment.get('release')!=str(OLD) or digest(OLD/'data/derived/budget.sqlite')!=contract['baseline_sha256']:
        raise ValueError('Le prédécesseur a changé. Aucun service modifié.')
    if get('http://127.0.0.1:8554/api/status').get('status')=='running':
        raise ValueError('Un audit est en cours. Relancer après sa fin ; aucun service modifié.')
    previous=json.loads(output('docker','compose','-f',OLD/'compose.yaml','config','--format','json'))
    audit=read(AUDIT);mounts=audit['services']['audit']['volumes']
    if mounts.count(str(OLD/'data')+':/reference/data:ro')!=1:raise ValueError('Référence audit inattendue')
    cid=output('docker','compose','-f',OLD/'compose.yaml','ps','-q','web')
    active=json.loads(output('docker','inspect',cid))[0]
    if active['Config']['Image']!=previous['services']['web']['image']:raise ValueError('Image active différente du Compose')
    if shutil.disk_usage(ROOT).free<1_500_000_000:raise ValueError('Au moins 1,5 Go libres nécessaires')
    if NEW.exists():
        if read(NEW/'STAGING.json').get('release_sha256')!=release_sha:raise ValueError('Autre préparation au même emplacement')
    else:
        NEW.mkdir(mode=0o755);write(NEW/'STAGING.json',dict(release_sha256=release_sha))
    if not (NEW/'rollback.json').exists():
        write(NEW/'rollback.json',dict(deployment=deployment,audit_compose=audit,audit_receipt=read('/opt/nos-deniers-audit/INSTALLED.json')))
    data=NEW/'data';data.mkdir(exist_ok=True)
    # Hard links preserve the predecessor; overlay files are atomically replaced, never edited in place.
    for src in (OLD/'data').rglob('*'):
        if src.is_symlink():raise ValueError('Lien symbolique inattendu dans les données')
        rel=src.relative_to(OLD/'data');target=data/rel
        if src.is_dir():target.mkdir(exist_ok=True)
        elif not target.exists():os.link(src,target)
    for rel in contract['data_files']:
        target=(data/rel).resolve()
        if not target.is_relative_to(data.resolve()):raise ValueError('Chemin hors livraison')
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_name(target.name+'.replacement');shutil.copyfile(BUNDLE/'data'/rel,tmp);tmp.chmod(0o644);tmp.replace(target)
    certificate=data/'derived/data-audit.json'
    if certificate.exists():certificate.unlink()  # Old certificate is not evidence for the new database.
    if digest(data/'derived/budget.sqlite')!=contract['database_sha256']:raise ValueError('Base copiée différente')
    image='lexmachine-budget:20260928-classeurs'
    run('docker','build','--network','none','--build-arg','BASE='+previous['services']['web']['image'],'-t',image,BUNDLE)
    check=['docker','run','--rm','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','1024m','--cpus','2','--tmpfs','/tmp:size=128m,mode=1777','--mount','type=bind,source='+str(data)+',target=/data,readonly','--mount','type=bind,source='+str(BUNDLE)+',target=/bundle,readonly',image]
    run(*check,'python','-m','unittest','discover','-s','tests','-p','test_*.py')
    run(*check,'python','/bundle/verify.py')
    config=json.loads(json.dumps(previous));web=config['services']['web'];web['image']=image
    found=0
    for v in web['volumes']:
        if v['target']=='/data':v['source']=str(data);found+=1
    if found!=1:raise ValueError('Montage des données inattendu')
    # Retrieval retains its exact image, mounts, indexes and running container.
    assert config['services']['retrieval']==previous['services']['retrieval']
    write(NEW/'compose.yaml',config)
    updated_audit=json.loads(json.dumps(audit));updated_audit['services']['audit']['volumes']=[str(data)+':/reference/data:ro' if v==str(OLD/'data')+':/reference/data:ro' else v for v in mounts]
    try:
        run('docker','compose','-f',NEW/'compose.yaml','up','-d','--no-deps','web')
        for attempt in range(24):
            try:
                if get('http://127.0.0.1:8552/api/bootstrap')['meta']['data_version']==contract['data_version']:break
            except Exception:pass
            time.sleep(2)
        else:raise ValueError('La nouvelle version ne démarre pas')
        run(sys.executable,BUNDLE/'verify.py','--http','http://127.0.0.1:8552')
        run(sys.executable,BUNDLE/'verify.py','--http','https://budget.lexmachine.net')
        write(AUDIT,updated_audit)
        run('docker','compose','-f',AUDIT,'up','-d','audit')
        for attempt in range(20):
            try:
                if get('http://127.0.0.1:8554/healthz')['service']=='nos-deniers-audit-independant':break
            except Exception:pass
            time.sleep(2)
        else:raise ValueError('Auditeur inaccessible après raccordement')
        aid=output('docker','compose','-f',AUDIT,'ps','-q','audit')
        actual=json.loads(output('docker','inspect',aid))[0]['Mounts']
        assert any(v['Destination']=='/reference/data' and v['Source']==str(data) and not v['RW'] for v in actual)
        assert digest(OLD/'data/derived/budget.sqlite')==contract['baseline_sha256']
    except BaseException:
        print('Échec de validation : restauration du site et du raccordement auditeur.');restore();raise
    receipt=read('/opt/nos-deniers-audit/INSTALLED.json');receipt.update(reference_database=str(data),data_version=contract['data_version'],reference_updated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    write(Path('/opt/nos-deniers-audit/INSTALLED.json'),receipt)
    write(ROOT/'deployment.json',dict(domain='budget.lexmachine.net',release=str(NEW),previous=str(OLD),state='published',fact_count=123483,source_count=4306,data_version=contract['data_version'],release_sha256=release_sha,rollback_command='sudo python3 '+str(BUNDLE/'install.py')+' --rollback'))
    print('Nos Deniers et la référence de son auditeur sont à jour. Index vectorisés conservés. Ancienne version conservée pour retour arrière.')

if __name__=='__main__':
    try:
        if os.geteuid()!=0 or socket.gethostname()!='vmi3274092':raise ValueError('Exécuter avec sudo sur le VPS prévu')
        with (ROOT/'.update.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);install()
    except Exception as e:print('Publication interrompue : '+str(e),file=sys.stderr);sys.exit(1)
