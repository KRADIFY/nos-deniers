"""Autonomous local index preparation with an exclusive lock, log and email receipt.

Uses no Codex model and no RunPod. On power loss, rerun this same command;
the builder resumes committed lots. No source corpus or public site is changed.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
GENERATION=Path('F:/LexMachine/NosDeniers/generation_tables_20260911')
OUTPUT=Path('D:/LexMachine/NosDeniers/search_20260919')
RUN=GENERATION/'runpod_bge_m3_20260912'
LOG=ROOT/'reports/finalisation-20260919'
RUNTIME=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
MAIL=ROOT.parent/'BRAINSTORMING_R23/private_corpus_api/send_codex_alert.ps1'


def write(path,data):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def notify(success,message):
    marker=LOG/('index-finished-email.json' if success else 'index-error-email.json')
    if success and marker.is_file() and json.loads(marker.read_text()).get('sent'):return
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(MAIL),
       '-Type','FIN' if success else 'BLOCAGE','-Subject','Nos Deniers : index prêt pour audit' if success else 'Nos Deniers : index interrompu',
       '-Body',message],capture_output=True,text=True,timeout=50)
    write(marker,dict(at=datetime.now(timezone.utc).isoformat(),sent=result.returncode==0,
                      error=None if result.returncode==0 else 'Envoi impossible ; consulter le bilan local.'))


def run():
    import msvcrt
    LOG.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
    lock=(LOG/'index-controller.lock').open('a+b');lock.seek(0)
    if os.fstat(lock.fileno()).st_size==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('Le traitement est déjà lancé. Consulter '+str(OUTPUT/'ETAT.txt'));return 0
    # Fail rather than run a second writer left alive by a controller crash.
    probe=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*build_retrieval_index.py*' } | Select-Object -ExpandProperty ProcessId"],capture_output=True,text=True)
    if probe.stdout.strip():
        print('Un indexeur est déjà actif : '+probe.stdout.strip());return 0
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'.runtime/retrieval-libs')
    env['PYTHONIOENCODING']='utf-8';env['PYTHONDONTWRITEBYTECODE']='1'
    env['OMP_NUM_THREADS']='4';env['OPENBLAS_NUM_THREADS']='1'
    args=[str(RUNTIME),'-u',str(ROOT/'tools/build_retrieval_index.py'),
          '--run',str(RUN),'--catalogue',str(GENERATION/'catalogue.sqlite'),
          '--budget',str(LOG/'budget-reference.sqlite'),'--output',str(OUTPUT),'--threads','4']
    begin=time.time();stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    stdout=LOG/('index-'+stamp+'.log')
    with stdout.open('a',encoding='utf-8') as stream:
        worker=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        write(LOG/'campaign.json',dict(state='running',pid=worker.pid,controller_pid=os.getpid(),log=str(stdout),started_at=datetime.now(timezone.utc).isoformat(),output=str(OUTPUT)))
        code=worker.wait()
    success=code==0 and (OUTPUT/'manifest.json').exists()
    manifest=json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8')) if success else {}
    report=dict(state='index_ready_for_audit' if success else 'interrupted',exit_code=code,
                finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.time()-begin),
                passages=manifest.get('passages'),documents=manifest.get('documents'),files=manifest.get('files',[]),
                output=str(OUTPUT),log=str(stdout),runpod_cost_usd=0,site_deployed=False,
                remaining='Valider la recherche de bout en bout, auditer et intégrer les chiffres, tester Docker et préparer la publication.')
    write(LOG/'campaign.json',report)
    message=('Index Nos Deniers préparé : '+str(manifest.get('passages'))+' passages.\n' if success else 'Préparation interrompue ; les lots déjà validés sont conservés.\n')
    message+='Dossier : '+str(OUTPUT)+'\nJournal : '+str(stdout)+'\nAucun RunPod lancé, coût RunPod : 0 $.\nLe site public est inchangé. L’audit financier et les tests de recherche restent à terminer.'
    (OUTPUT/'BILAN.txt').write_text(message,encoding='utf-8')
    print(message)
    try:notify(success,message)
    except Exception as exc:write(LOG/'index-email-error.json',dict(sent=False,error_type=type(exc).__name__))
    return code


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','status'],nargs='?',default='status')
    args=parser.parse_args()
    if args.command=='run':sys.exit(run())
    for path in [LOG/'campaign.json',OUTPUT/'ETAT.txt']:
        if path.exists():print(path.read_text(encoding='utf-8'))
