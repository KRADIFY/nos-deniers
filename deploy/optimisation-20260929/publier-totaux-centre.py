"""Publication ciblée des avertissements de total et du compteur centré."""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT=Path('/opt/nos-deniers')
COMPOSE=ROOT/'compose.yaml'
OLD='lexmachine-budget:20260929-optimisee-notices-v3'
NEW='lexmachine-budget:20261001-totaux-centre'
SERVICES={'web1':8552,'web2':8556,'web3':8557,'web4':8558}
STAGING=ROOT/'staging/totaux-centre-20261001'

def run(*args):
    return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()

def ready(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/readyz',timeout=15) as response:
        return json.load(response).get('ready') is True

def public(path):
    return run('curl','-fsS','--max-time','30','--resolve','budget.lexmachine.net:443:127.0.0.1','https://budget.lexmachine.net'+path)

def deploy_service(name,port):
    run('docker','compose','-f',str(COMPOSE),'up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','120',name)
    for _ in range(20):
        try:
            if ready(port):return
        except Exception:pass
        time.sleep(1)
    raise RuntimeError(f'{name} ne répond pas')

def main():
    if os.geteuid()!=0 or run('hostname')!='vmi3304602':raise SystemExit('Mauvais serveur ou droits insuffisants.')
    if not ready(8552) or not ready(18674):raise SystemExit('Version actuelle ou candidate indisponible.')
    original=COMPOSE.read_bytes()
    text=original.decode('utf-8')
    if text.count('image: '+OLD)!=1 or 'image: '+NEW in text:raise SystemExit('Version active inattendue.')
    if not run('docker','image','inspect','--format','{{.Id}}',NEW):raise SystemExit('Image candidate absente.')
    STAGING.mkdir(parents=True,exist_ok=True)
    backup=STAGING/'compose.before.yaml'
    if backup.exists():raise SystemExit('Sauvegarde déjà présente; vérifier avant une nouvelle publication.')
    backup.write_bytes(original)
    updated=text.replace('image: '+OLD,'image: '+NEW,1)
    temp=COMPOSE.with_suffix('.totaux-tmp')
    temp.write_text(updated,encoding='utf-8')
    os.chmod(temp,0o644)
    temp.replace(COMPOSE)
    try:
        run('docker','compose','-f',str(COMPOSE),'config','-q')
        for name,port in SERVICES.items():
            deploy_service(name,port)
            print(name,'prêt',flush=True)
        if not json.loads(public('/readyz'))['ready']:raise RuntimeError('Site public indisponible.')
        if 'Ce total comprend' not in public('/assets/explorer.js'):raise RuntimeError('Avertissement absent du JavaScript public.')
        if 'left:50%;top:50%' not in public('/assets/explorer.css'):raise RuntimeError('Compteur centré absent du CSS public.')
        if 'src="/activity/script.js"' not in public('/'):raise RuntimeError('Collecte des visites absente de l’accueil.')
        ids={name:run('docker','inspect','--format','{{.Image}}','nos-deniers-public-'+name+'-1') for name in SERVICES}
        if len(set(ids.values()))!=1:raise RuntimeError('Images différentes parmi les quatre instances.')
        receipt={'at':datetime.now().isoformat(),'previous':OLD,'active':NEW,'image_id':next(iter(ids.values())),
                 'services':list(SERVICES),'backup':str(backup),'data_unchanged':True,'vectors_unchanged':True,
                 'monitoring_preserved':True}
        (STAGING/'PUBLISHED.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    except Exception:
        print('Échec : retour à la version précédente.',flush=True)
        restore=COMPOSE.with_suffix('.rollback-tmp');restore.write_bytes(original);os.chmod(restore,0o644);restore.replace(COMPOSE)
        for name,port in SERVICES.items():
            try:deploy_service(name,port)
            except Exception as error:print('Retour arrière incomplet',name,type(error).__name__,flush=True)
        raise

if __name__=='__main__':main()
