"""Install only the independent auditor and the requested website link on the VPS."""
import hashlib,json,os,re,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
from site_link import patch
DOMAIN='auditnosdeniers.lexmachine.net'
AUDIT_PORT=8554
UPSTREAM=f'http://127.0.0.1:{AUDIT_PORT}'
ROOT=Path('/opt/nos-deniers-audit');BUNDLE=Path(__file__).resolve().parent
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def capture(args,**kw):return subprocess.check_output(args,text=True,**kw).strip()
def write(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,'utf-8');path.chmod(0o644)
def get(url):
    with urllib.request.urlopen(url,timeout=20) as r:return r.read()
def healthy(url,tries=30):
    for i in range(tries):
        try:return json.loads(get(url))
        except Exception:
            if i==tries-1:raise
            time.sleep(2)
def nginx_config(tls):
    base=f'''# Managed by Nos Deniers independent audit installer.
server {{
 listen 80;
 server_name {DOMAIN};
 location ^~ /.well-known/acme-challenge/ {{ root /var/www/nos-deniers-audit-acme; }}
 location / {{ {'return 301 https://'+DOMAIN+'$request_uri;' if tls else 'proxy_pass '+UPSTREAM+';'} }}
}}
'''
    if tls:base+=f'''server {{
 listen 443 ssl;
 server_name {DOMAIN};
 ssl_certificate /etc/letsencrypt/live/{DOMAIN}/fullchain.pem;
 ssl_certificate_key /etc/letsencrypt/live/{DOMAIN}/privkey.pem;
 client_max_body_size 2k;
 location / {{
  proxy_pass {UPSTREAM};
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_read_timeout 30s;
 }}
}}
'''
    return base
def check_audit_port():
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1',AUDIT_PORT))
        return
    except OSError as error:
        # Allow a repeat installation only if our own running audit container
        # already owns the exact loopback mapping. Never stop another service.
        try:
            info=json.loads(capture(['docker','inspect','nos-deniers-audit-audit-1'],stderr=subprocess.DEVNULL))[0]
            labels=info.get('Config',{}).get('Labels',{})
            ports=info.get('NetworkSettings',{}).get('Ports',{}).get('8095/tcp') or []
            if (info.get('State',{}).get('Running')
                and labels.get('com.docker.compose.project')=='nos-deniers-audit'
                and labels.get('com.docker.compose.service')=='audit'
                and any(p.get('HostIp')=='127.0.0.1' and p.get('HostPort')==str(AUDIT_PORT) for p in ports)):
                return
        except (subprocess.CalledProcessError,ValueError,KeyError,IndexError):
            pass
        raise RuntimeError(f'Le port local {AUDIT_PORT} est occupé ou inaccessible. Aucun service modifié ; choisir un port libre pour l’auditeur.') from error

def main():
    if os.geteuid()!=0:raise RuntimeError('Lancer avec sudo python3 install.py.')
    manifest=json.loads((BUNDLE/'FILES.json').read_text())
    for name,expected in manifest.items():
        p=(BUNDLE/name).resolve()
        if not p.is_relative_to(BUNDLE) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise RuntimeError('Fichier de livraison incorrect : '+name)
    if socket.gethostbyname(DOMAIN)!='109.199.112.132':raise RuntimeError('DNS A non conforme. Aucun service modifié.')
    for cmd in ('docker','nginx','certbot'):run(['which',cmd],stdout=subprocess.DEVNULL)
    check_audit_port()
    deployment=json.loads(Path('/opt/lexmachine-budget/deployment.json').read_text())
    release=Path(deployment['release']).resolve()
    if not release.is_relative_to('/opt/lexmachine-budget/releases'):raise RuntimeError('Chemin de base inattendu.')
    production=get('https://budget.lexmachine.net/api/bootstrap');meta=json.loads(production)['meta']
    if meta['data_version']!=deployment['data_version']:raise RuntimeError('La version publique ne correspond pas au déploiement.')
    web='lexmachine-budget-public-web-1'
    inspection=json.loads(capture(['docker','inspect',web]))[0]
    labels=inspection['Config']['Labels'];original_image=inspection['Config']['Image']
    configs=labels['com.docker.compose.project.config_files'].split(',')
    if len(configs)!=1:raise RuntimeError('Plusieurs fichiers Compose pour le site : vérifier avant installation.')
    sitecompose=Path(configs[0]);original_compose=sitecompose.read_text()
    if not sitecompose.resolve().is_relative_to('/opt/lexmachine-budget'):raise RuntimeError('Compose hors du dossier attendu.')
    owner=ROOT/'OWNER.json'
    if ROOT.exists() and not owner.exists():raise RuntimeError('Dossier existant non géré : '+str(ROOT))
    ROOT.mkdir(parents=True,exist_ok=True)
    write(owner,json.dumps(dict(service='nos-deniers-audit-independant')))
    stamp=time.strftime('%Y%m%d-%H%M%S');target=ROOT/'releases'/stamp
    target.mkdir(parents=True)
    for name in list(manifest)+['FILES.json']:
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BUNDLE/name,dest)
    for p in target.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
    backup=ROOT/'backups'/stamp;backup.mkdir(parents=True)
    shutil.copy2(sitecompose,backup/'budget-compose.yaml')
    registries=target/'reference'/'registries';registries.mkdir(parents=True)
    run(['docker','cp',web+':/app/budget_service/data/.',str(registries)])
    for p in registries.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
    state=ROOT/'state';state.mkdir(exist_ok=True);os.chown(state,10001,10001);state.chmod(0o750)
    # Snapshot is made by the non-root worker. Only these reference paths are mounted.
    database=release/'data'
    if not (database/'derived/budget.sqlite').is_file():raise RuntimeError('Base structurée absente.')
    image='nos-deniers-audit:'+stamp
    run(['docker','build','-t',image,str(target)])
    isolated=['docker','run','--rm','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:size=384m,mode=1777','--shm-size','256m']
    run(isolated+['--mount','type=bind,source='+str(target)+',target=/tests,readonly',image,'python','-m','unittest','discover','-s','/tests','-p','test_*.py','-q'])
    smoke="const {chromium}=require(process.env.AUDIT_NODE_MODULES+'/playwright');(async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.AUDIT_CHROME});const p=await b.newPage();await p.setContent('<h1>Test audit</h1>');if(await p.locator('h1').textContent()!=='Test audit')throw Error('Navigateur invalide');await b.close();console.log('Navigateur Docker vérifié.');})().catch(e=>{console.error(e);process.exit(1)})"
    run(isolated+[image,'node','-e',smoke])
    config={'name':'nos-deniers-audit','services':{'audit':{'image':image,'restart':'unless-stopped','user':'10001:10001',
      'read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],'mem_limit':'1536m','cpus':1.5,'pids_limit':256,
      'ports':[f'127.0.0.1:{AUDIT_PORT}:8095'],'shm_size':'256m','tmpfs':['/tmp:size=384m,mode=1777'],
      'volumes':[str(database)+':/reference/data:ro',str(registries)+':/reference/registries:ro',str(state)+':/audit-data'],
      'environment':{'AUDIT_PUBLIC_URL':'https://'+DOMAIN,'AUDIT_TARGET_URL':'https://budget.lexmachine.net','AUDIT_REQUEST_DELAY':'0.3','TZ':'Europe/Paris'}}}}
    compose=ROOT/'compose.json'
    if compose.exists():shutil.copy2(compose,backup/'audit-compose.json')
    write(compose,json.dumps(config,indent=2))
    # Validate actual read-only mounts before activating anything public.
    run(['docker','compose','-f',str(compose),'run','--rm','--no-deps','audit','python','-c',
      "from pathlib import Path; import sqlite3; p=Path('/reference/data/derived/budget.sqlite'); c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); assert c.execute('select count(*) from facts').fetchone()[0]>0; assert Path('/reference/registries/maprimerenov.json').is_file(); print('Base du VPS lisible en lecture seule.')"])
    run(['docker','compose','-f',str(compose),'up','-d','audit'])
    health=healthy(UPSTREAM+'/healthz')
    if health.get('service')!='nos-deniers-audit-independant':raise RuntimeError('Mauvais service sur le port audit.')
    conf=Path('/etc/nginx/sites-available')/DOMAIN;enabled=Path('/etc/nginx/sites-enabled')/DOMAIN
    if conf.exists():
        if 'Managed by Nos Deniers independent audit installer.' not in conf.read_text():raise RuntimeError('Configuration Nginx préexistante : intervention manuelle nécessaire.')
        shutil.copy2(conf,backup/'nginx.conf')
    acme=Path('/var/www/nos-deniers-audit-acme');acme.mkdir(parents=True,exist_ok=True)
    write(conf,nginx_config(False))
    if not enabled.exists():enabled.symlink_to(conf)
    run(['nginx','-t']);run(['systemctl','reload','nginx'])
    run(['certbot','certonly','--webroot','-w',str(acme),'-d',DOMAIN,'--non-interactive','--agree-tos','--register-unsafely-without-email'])
    write(conf,nginx_config(True));run(['nginx','-t']);run(['systemctl','reload','nginx'])
    healthy('https://'+DOMAIN+'/healthz')
    # Build a tiny overlay from the running site's exact image: only HTML/CSS link.
    overlay=target/'site-link';(overlay/'public/assets').mkdir(parents=True)
    for name in ('explorer.html','assets/explorer.css'):
        run(['docker','cp',web+':/app/public/'+name,str(overlay/'public'/name)])
    hp=overlay/'public/explorer.html';cp=overlay/'public/assets/explorer.css'
    before_h=hp.read_text();before_c=cp.read_text();h,c=patch(before_h,before_c)
    if (h,c)!=(before_h,before_c):
        hp.write_text(h,'utf-8');cp.write_text(c,'utf-8')
        for p in overlay.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
        link_image='lexmachine-budget:audit-link-'+stamp
        write(overlay/'Dockerfile','FROM '+original_image+'\nCOPY public/explorer.html /app/public/explorer.html\nCOPY public/assets/explorer.css /app/public/assets/explorer.css\n')
        run(['docker','build','-t',link_image,str(overlay)])
        image_pattern=r'(?m)^(\s+image:\s*)'+re.escape(original_image)+r'\s*$'
        replacement,count=re.subn(image_pattern,lambda m:m[1]+link_image,original_compose)
        if count!=1:raise RuntimeError('Image web non isolable dans Compose ; le service audit reste disponible, lien non ajouté.')
        try:
            write(sitecompose,replacement)
            run(['docker','compose','-f',str(sitecompose),'up','-d','--no-deps','web'],cwd=sitecompose.parent)
            after=healthy('http://127.0.0.1:8552/api/bootstrap')
            if after['meta']['data_version']!=meta['data_version']:raise RuntimeError('La base a changé pendant installation.')
            if b'auditnosdeniers.lexmachine.net' not in get('https://budget.lexmachine.net/'):raise RuntimeError('Lien public non visible.')
        except Exception:
            write(sitecompose,original_compose)
            run(['docker','compose','-f',str(sitecompose),'up','-d','--no-deps','web'],cwd=sitecompose.parent)
            raise
    receipt=dict(at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),url='https://'+DOMAIN+'/',reference_database=str(database),data_version=meta['data_version'],
      site_change='Lien de navigation uniquement ; chiffres, JavaScript et base inchangés.',backup=str(backup),audit_image=image,audit_port=AUDIT_PORT)
    write(ROOT/'INSTALLED.json',json.dumps(receipt,ensure_ascii=False,indent=2))
    print('Audit indépendant publié : https://'+DOMAIN+'/\nLien ajouté au site. Aucun chiffre ni index vectoriel modifié.\nCliquer sur Lancer la vérification pour démarrer le contrôle complet.',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:print('Installation interrompue : '+str(e),file=sys.stderr);sys.exit(1)
