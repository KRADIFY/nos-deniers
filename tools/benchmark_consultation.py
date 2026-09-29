"""Local Docker comparison only; never load-tests the public VPS."""
import concurrent.futures as cf
import gzip, hashlib, io, json, statistics, subprocess, sys, threading, time, urllib.request, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/consultation-20260929'
DATA=ROOT/'reports/integration-annexes-20260928/data'
NAMES=['budget-consultation-baseline-test','budget-consultation-optimized-test']
PORTS=[18671,18672]
IMAGES=['lexmachine-budget:20260929-navigation-preuves','lexmachine-budget:20260929-consultation-chaude']
REPORT=json.loads((OUT/'benchmark.json').read_text()) if '--resume' in sys.argv else {'local_only':True,'vps_capacity_certified':False,'checks':[],'waves':[]}
if '--resume' in sys.argv:
    REPORT['baseline_load_failure']={'clients':5,'error':REPORT.pop('error',None),'timeout_seconds':90}
    REPORT.pop('passed',None)

def save():
    (OUT/'benchmark.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')

def run(*args):return subprocess.check_output(list(args),text=True).strip()

def get(port,path):
    t=time.monotonic()
    req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,headers={'Accept-Encoding':'gzip'})
    with urllib.request.urlopen(req,timeout=90) as r:
        data=r.read()
        if r.headers.get('Content-Encoding')=='gzip':data=gzip.decompress(data)
        return data,time.monotonic()-t

def identity(path,data):
    if path.startswith('/api/export.xlsx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return hashlib.sha256(b''.join(n.encode()+z.read(n) for n in sorted(z.namelist()))).hexdigest()
    return hashlib.sha256(data).hexdigest()

def wait_ready(port):
    for _ in range(120):
        try:get(port,'/readyz');return
        except Exception:time.sleep(.5)
    raise RuntimeError('Startup failed')

def wave(port,n,path,expected):
    barrier=threading.Barrier(n)
    def one(_):
        barrier.wait();body,seconds=get(port,path)
        if identity(path,body)!=expected:raise AssertionError('Different response under concurrency')
        return seconds
    with cf.ThreadPoolExecutor(n) as pool:values=list(pool.map(one,range(n)))
    return {'port':port,'clients':n,'p50_seconds':round(statistics.median(values),3),'max_seconds':round(max(values),3),'errors':0}

created=[]
try:
    for name,port,img in zip(NAMES,PORTS,IMAGES):
        run('docker','run','-d','--name',name,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','768m','--cpus','2','--pids-limit','64','--tmpfs','/tmp:size=32m,mode=1777',
            '-e','BUDGET_KEEP_WARM_SECONDS=60','-p',f'127.0.0.1:{port}:8080',
            '--mount',f'type=bind,source={DATA},target=/data,readonly',img)
        created.append(name);wait_ready(port)
    paths=['/api/bootstrap','/api/explorer','/api/explorer?measure=AE','/api/explorer?scope=TA',
           '/api/explorer?scope=TA&measure=AE','/api/explorer?topic=maprimerenov',
           '/api/explorer?topic=maprimerenov&topic_mode=without&scope=TA',
           '/api/explorer?scope=TA&exclude=%5B%22TA%2F345%22%5D',
           '/api/explorer?scope=TA&constant=1&base=2017',
           '/api/explorer?budget=BA&start=2017&end=2018',
           '/api/explorer?budget=CAS&start=2024&end=2026',
           '/api/explorer?budget=CCF&measure=AE&start=2025&end=2025',
           '/api/provenance?scope=TA&cell_scope=TA%2F174&year=2023&stage=EXEC',
           '/api/provenance?scope=TA&cell_scope=TA%2F174&year=2025&stage=LFI',
           '/api/reserves?scope=TA','/api/events?scope=TA','/api/rap-movements?scope=TA&view=summary',
           '/api/documents?format=pdf&year=2024','/api/export?scope=TA','/api/export.xlsx?scope=TA']
    for path in ([] if '--resume' in sys.argv else paths):
        old,ts=get(PORTS[0],path);new,tn=get(PORTS[1],path)
        assert identity(path,old)==identity(path,new),path
        REPORT['checks'].append({'path':path,'identical':True,'before_seconds':round(ts,3),'after_seconds':round(tn,3)})
        save();print('IDENTICAL',path,round(ts,2),round(tn,2),flush=True)
    path='/api/explorer';body,_=get(PORTS[0],path);expected=identity(path,body)
    for n in (() if '--resume' in sys.argv else (1,5)):
        r=wave(PORTS[0],n,path,expected);REPORT['waves'].append(r);save();print('BASELINE',r,flush=True)
    get(PORTS[1],path)
    for n in (1,5,10,20):
        r=wave(PORTS[1],n,path,expected);REPORT['waves'].append(r);save();print('OPTIMIZED',r,flush=True)
    path='/api/explorer?scope=TA%2F174&start=2019&end=2020'
    before=json.loads(get(PORTS[1],'/healthz')[0])['consultation']['cache']
    original,_=get(PORTS[0],path)
    r=wave(PORTS[1],10,path,identity(path,original));REPORT['cold_shared_wave']=r
    after=json.loads(get(PORTS[1],'/healthz')[0])['consultation']['cache']
    REPORT['cold_shared_calculations']=after['misses']-before['misses']
    assert REPORT['cold_shared_calculations']==1,REPORT['cold_shared_calculations']
    # Observe a second automatic keep-warm cycle, without any manual trigger.
    for _ in range(150):
        state=json.loads(get(PORTS[1],'/healthz')[0])['consultation']
        if state['keep_warm']['completed_cycles']>=2:break
        time.sleep(1)
    REPORT['runtime']=state
    assert state['keep_warm']['completed_cycles']>=2
    assert state['keep_warm']['state']=='warm'
    assert state['cache']['bytes']<=64*1024*1024
    REPORT['containers']=json.loads(run('docker','inspect',*NAMES))
    REPORT['containers']=[{'name':x['Name'],'oom_killed':x['State']['OOMKilled'],'memory_limit':x['HostConfig']['Memory'],'cpu_limit':x['HostConfig']['NanoCpus']} for x in REPORT['containers']]
    REPORT['passed']=True;save();print('PASS',str(OUT/'benchmark.json'),flush=True)
except BaseException as exc:
    REPORT.update(passed=False,error=str(exc));save();raise
finally:
    for name in created:
        try:
            (OUT/(name+'.log')).write_text(run('docker','logs',name),encoding='utf-8')
            run('docker','rm','-f',name)
        except Exception as exc:print('CLEANUP',name,exc,flush=True)
