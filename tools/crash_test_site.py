"""Reproducible local application crash test. Read-only HTTP/SQL, no AI or GPU.
Run again with the same --output to resume. Use --full-tree for all programme scopes.
"""
from pathlib import Path
import argparse,concurrent.futures,csv,datetime,hashlib,html,io,json,math,os,sqlite3,statistics,subprocess,sys,time,traceback,urllib.request,urllib.parse,urllib.error,zipfile
from decimal import Decimal,ROUND_HALF_UP
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_NODE=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
SCHEMA='nos-deniers-application-crash-test-1'

def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(v):return hashlib.sha256(v).hexdigest()
def stamp():return datetime.datetime.now().astimezone().isoformat()
def save(p,v):
 t=Path(str(p)+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf-8');os.replace(t,p)
def command(argv,timeout=90,env=None):
 p=subprocess.run(argv,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace',timeout=timeout,env=env)
 if p.returncode:raise RuntimeError(f'{Path(argv[0]).name}: '+p.stderr[-3500:]+p.stdout[-1500:])
 return p.stdout

def request(base,route,method='GET'):
 started=time.perf_counter()
 try:r=urllib.request.urlopen(urllib.request.Request(base+route,method=method),timeout=30)
 except urllib.error.HTTPError as e:r=e
 with r:
  body=r.read(32*1024*1024+1);assert len(body)<=32*1024*1024,'Unexpected response >32 MiB'
  return dict(status=r.status,headers=dict(r.headers),body=body,seconds=time.perf_counter()-started)
def obj(response):
 assert response['status']==200,f'HTTP {response["status"]}: {response["body"][:200]!r}'
 return json.loads(response['body'])
def query(params):return urllib.parse.urlencode({k:(json.dumps(v) if isinstance(v,list) else int(v) if isinstance(v,bool) else v) for k,v in params.items()})
def signature(data):return [(r['year'],s,v.get('nominal_cents'),v.get('nominal'),v.get('value'),v.get('status')) for r in data['totals'] for s,v in r.items() if s in data['stages']]

def check_derived(data,indices):
 """Independent arithmetic, without importing the application formulas."""
 checks=0
 for series in [data['totals']]+[r['series'] for r in data['rows']]:
  by_year={r['year']:r for r in series}
  for annual in series:
   for name,result in annual.get('comparisons',{}).items():
    a,b=(annual[s] for s in result['operands']);wanted=None
    valid=all(c.get('value') is not None and c['status'] in ('ok','excluded') for c in (a,b))
    if valid and name!='CONSUMPTION':wanted=Decimal(str(a['value']))-Decimal(str(b['value']))
    elif valid and b['nominal']!=0:wanted=(Decimal(str(a['nominal']))/Decimal(str(b['nominal']))*100).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
    assert result['value'] is None if wanted is None else Decimal(str(result['value']))==wanted,('comparison',annual['year'],name,result,wanted)
    checks+=1
   for stage,rates in annual.get('evolution',{}).items():
    for name,result in rates.items():
     before=by_year.get(result['reference_year']);a=annual[stage];b=before[stage] if before else None;wanted=None
     ac=a.get('nominal_cents');bc=b.get('nominal_cents') if b else None
     valid=b is not None and ac is not None and bc is not None and bc>0 and all(c.get('nominal_status',c['status']) in ('ok','excluded') for c in (a,b))
     real=name!='nominal_yoy';ia=indices.get(str(annual['year']));ib=indices.get(str(result['reference_year']))
     if valid and (not real or (ia and ib)):
      ratio=Decimal(ac)/Decimal(bc)
      if real:ratio*=Decimal(str(ib))/Decimal(str(ia))
      wanted=((ratio-1)*100).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
     assert result['value'] is None if wanted is None else Decimal(str(result['value']))==wanted,('evolution',annual['year'],stage,name,result,wanted)
     checks+=1
 return checks

def sql_reference(container):
 code="""import sqlite3,json,hashlib; from pathlib import Path
p=Path('/data/derived/budget.sqlite'); c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
rows=c.execute('select year,stage,measure,budget,mission,program,sum(cents) from facts group by year,stage,measure,budget,mission,program').fetchall()
meta={k:json.loads(v) for k,v in c.execute('select key,value from meta')}
print(json.dumps(dict(rows=rows,fact_count=c.execute('select count(*) from facts').fetchone()[0],sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),indices=meta['indices'],data_version=meta.get('data_version'),built_at=meta['built_at'],read_only=True)))"""
 return json.loads(command(['docker','exec',container,'python','-c',code]))

class Campaign:
 def __init__(self,args):
  self.args=args;self.base=args.base_url.rstrip('/');u=urllib.parse.urlsplit(self.base)
  if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.path:raise ValueError('This load test is restricted to a local HTTP site')
  self.out=args.output.resolve();self.out.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(self.out/'checkpoints.sqlite');self.db.execute('create table if not exists cases(id text primary key,kind text,status text,seconds real,result text,checked_at text)')
  self.ref=sql_reference(args.container);self.boot=obj(request(self.base,'/api/bootstrap'));self.assets={p:sha(request(self.base,p)['body']) for p in ['/','/assets/explorer.js','/assets/explorer.css']}
  self.identity=dict(schema=SCHEMA,base_url=self.base,sql_sha256=self.ref['sha256'],assets=self.assets,full_tree=args.full_tree,script_sha256=sha(Path(__file__).read_bytes()),numeric_worker_sha256=sha((ROOT/'tools/crash_test_numeric_worker.py').read_bytes()),load_enabled=not args.no_load)
  ip=self.out/'identity.json'
  if ip.exists() and json.loads(ip.read_text('utf-8'))!=self.identity:raise ValueError('The site/data/test changed. Preserve this report and choose a new --output directory.')
  save(ip,self.identity);save(self.out/'sql-reference.json',self.ref)
  self.done={r[0] for r in self.db.execute('select id from cases')};self.failures=0;self.expected={};self.scopes={}
  for year,stage,measure,budget,mission,program,amount in self.ref['rows']:
   if year==2026 and mission=='M26985a5788':mission='MB'
   for path in ('',mission,mission+'/'+program):
    key=(year,stage,measure,budget,path);self.expected[key]=self.expected.get(key,0)+amount
   self.scopes[(budget,mission)]=max(year,self.scopes.get((budget,mission),0))
  assert self.boot['meta']['fact_count']==self.ref['fact_count'],'Site and SQL reference have different counts'
 def emit(self,phase,**kw):
  state=dict(at=stamp(),phase=phase,completed=len(self.done),**kw);save(self.out/'progress.json',state)
  (self.out/'ETAT.txt').write_text(f"{state['at']} — {phase}\nScénarios enregistrés : {len(self.done)}\nReprise : relancer le même lanceur. Aucun calcul IA ou GPU.\n",'utf-8');print(dump(state),flush=True)
 def case(self,ident,kind,fn):
  if ident in self.done:return
  started=time.perf_counter()
  try:result=fn() or {};status='pass'
  except Exception as e:status='failure';result=dict(error=str(e),traceback=traceback.format_exc());self.failures+=1
  elapsed=time.perf_counter()-started
  with self.db:self.db.execute('insert into cases values(?,?,?,?,?,?)',(ident,kind,status,elapsed,dump(result),stamp()))
  self.done.add(ident)
  if status!='pass' or len(self.done)%20==0:self.emit(kind,last=ident,status=status)
 def explorer(self,p):return obj(request(self.base,'/api/explorer?'+query(p)))
 def check_tree(self,p):
  d=self.explorer(p);checks=0;missing=0
  for scope,series in [(p.get('scope',''),d['totals'])]+[(r['id'],r['series']) for r in d['rows']]:
   for row in series:
    for stage in d['stages']:
     cell=row[stage];expected=self.expected.get((row['year'],stage,p['measure'],p['budget'],scope));actual=cell.get('nominal_cents')
     if scope.count('/')<=1:
      assert actual==expected,(scope,row['year'],stage,'SQL cents',actual,expected)
      if expected is not None:assert Decimal(str(cell['nominal'])).quantize(Decimal('.01'))==Decimal(expected)/100
      checks+=1
     if cell.get('value') is None:
      missing+=1;assert cell['status'] not in ('ok','excluded') and cell.get('reason'),('Missing amount without explanation',scope,stage)
     else:assert math.isfinite(cell['value']) and cell.get('sources') or cell.get('status')=='excluded'
  return dict(route='/api/explorer?'+query(p),cells_compared_to_sql=checks,derived_arithmetic_checks=check_derived(d,self.ref['indices']),unavailable_cells=missing,response_signature=sha(dump(signature(d)).encode()),rows=len(d['rows']))
 def roundtrip(self,p):
  d=self.explorer(p);rows=[(p.get('scope',''),d['totals'])]+[(r['id'],r['series']) for r in d['rows']]
  expected={(scope,r['year'],d['stages'][s]):r[s]['value'] for scope,series in rows for r in series for s in d['stages']}
  q=query(p);data=request(self.base,'/api/export?'+q);assert data['status']==200
  csv_rows=list(csv.DictReader(io.StringIO(data['body'].decode('utf-8-sig')),delimiter=';'));assert len(csv_rows)==len(expected)
  for row in csv_rows:
   wanted=expected[(row['Code'],int(row['Année']),row['Étape'])];got=row['Montant EUR']
   assert (got=='') if wanted is None else Decimal(got.replace(',','.'))==Decimal(str(wanted))
  x=request(self.base,'/api/export.xlsx?'+q);assert x['status']==200
  import xml.etree.ElementTree as ET
  ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  with zipfile.ZipFile(io.BytesIO(x['body'])) as z:
   assert z.testzip() is None
   actual=ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//s:row',ns)[1:];assert len(actual)==len(expected)
   for rr in actual:
    cells={rekey.get('r').rstrip('0123456789'):rekey for rekey in rr}
    def cell(k):
     el=cells.get(k)
     if el is None:return None
     t=el.find('s:v',ns);return t.text if t is not None else ''.join(el.itertext())
    wanted=expected[(cell('D') or '',int(cell('E')),cell('G'))];got=cell('H')
    assert got is None if wanted is None else Decimal(got)==Decimal(str(wanted))
  selection=obj(request(self.base,'/api/selection?'+q));assert signature(selection)==signature(d) and selection['selection_id']==d['selection_id']
  return dict(rows=len(expected),csv_xlsx_json_agree=True,derived_arithmetic_checks=check_derived(d,self.ref['indices']))
 def invariants(self,p):
  base=self.explorer(p);indices=self.ref['indices'];converted=self.explorer(p|dict(constant=1,base=2025));checked=0
  for nominal,real in zip(base['totals'],converted['totals']):
   for stage in base['stages']:
    a,b=nominal[stage],real[stage];assert a.get('nominal_cents')==b.get('nominal_cents')
    if a.get('nominal_cents') is None:continue
    year=str(nominal['year']);wanted=None if year not in indices else (Decimal(a['nominal_cents'])*Decimal(str(indices['2025']))/Decimal(str(indices[year]))).quantize(Decimal(1),rounding=ROUND_HALF_UP)/100
    assert b['value'] is None if wanted is None else abs(Decimal(str(b['value']))-wanted)<Decimal('.005');checked+=1
  if base['rows']:
   target=base['rows'][0]['id'];excluded=self.explorer(p|dict(exclude=[target]));duplicate=self.explorer(p|dict(exclude=[target,target]));assert signature(excluded)==signature(duplicate)
   for a,b,child in zip(base['totals'],excluded['totals'],base['rows'][0]['series']):
    for s in base['stages']:
     if a[s].get('nominal_cents') is not None and child[s].get('nominal_cents') is not None and b[s].get('nominal_cents') is not None:assert a[s]['nominal_cents']-child[s]['nominal_cents']==b[s]['nominal_cents']
   assert signature(self.explorer(p))==signature(base),'Reactivation did not restore the selection'
  return dict(inflation_checks=checked,exclusion_reactivation_and_duplicate_exclusions=True,derived_arithmetic_checks=check_derived(base,self.ref['indices'])+check_derived(converted,self.ref['indices']))
 def basic(self,route,status=200,method='GET'):
  r=request(self.base,route,method);assert r['status']==status,(route,r['status'],status)
  if method=='HEAD':assert r['body']==b''
  if status>=400:assert b'Traceback (most recent call last)' not in r['body']
  return dict(route=route,http_status=r['status'],response_seconds=r['seconds'])
 def load(self,workers):
  routes=['/api/explorer?start=2024&end=2024&scope=TA&measure=CP','/api/explorer?start=2021&end=2024&topic=maprimerenov&measure=AE','/api/rap-movements?start=2024&end=2024&scope=TA&view=summary&limit=100','/api/reserves?start=2023&end=2024&scope=TA']
  baselines={r:sha(request(self.base,r)['body']) for r in routes}
  def one(i):
   route=routes[i%len(routes)];r=request(self.base,route);assert r['status']==200 and sha(r['body'])==baselines[route],('Parallel result changed',route,r['status']);return r['seconds']
  with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:times=list(pool.map(one,range(workers*8)))
  times.sort();self.basic('/healthz')
  return dict(concurrency=workers,requests=len(times),p50_seconds=statistics.median(times),p95_seconds=times[math.ceil(.95*len(times))-1],maximum_seconds=max(times),same_responses_as_serial=True,local_only=True)
 def node_test(self,name,browser=False):
  src=ROOT/'tests'/name;node=self.args.node
  if not browser:assert sha((ROOT/'public/assets/explorer.js').read_bytes())==self.assets['/assets/explorer.js'],'Local JavaScript differs from tested service'
  env=os.environ.copy();env['NODE_PATH']=str(node.parent.parent/'node_modules')
  if browser:
   out=self.out/'browser'/src.stem;out.mkdir(parents=True,exist_ok=True)
   text=src.read_text('utf-8');import re
   text,n=re.subn(r"const out=path.resolve\(__dirname,'[^']+'\)",lambda _: 'const out='+json.dumps(str(out)),text,count=1);assert n==1
   script=out/name;script.write_text(text,'utf-8');args=[str(node),str(script)]
  else:args=[str(node),str(src)]
  text=command(args,timeout=180,env=env);(self.out/(src.stem+'.log')).write_text(text,'utf-8')
  return dict(test=name,browser=browser,log=src.stem+'.log',output=text[-500:])
 def numeric(self):
  script=(ROOT/'tools/crash_test_numeric_worker.py').read_text('utf-8')
  self.emit('numeric_reference_checks')
  with (self.out/'numeric-stderr.log').open('w',encoding='utf-8') as errors:
   proc=subprocess.Popen(['docker','exec','-i',self.args.container,'python','-',json.dumps(sorted(k for k in self.done if k.startswith('numeric:')))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',cwd=ROOT)
   try:
    proc.stdin.write(script);proc.stdin.close();started=time.perf_counter()
    for line in proc.stdout:
     result=json.loads(line);key=result['id'];elapsed=time.perf_counter()-started;started=time.perf_counter()
     with self.db:self.db.execute('insert into cases values(?,?,?,?,?,?)',(key,result['kind'],result['status'],elapsed,dump(result['result']),stamp()))
     self.done.add(key)
     if result['status']!='pass' or len(self.done)%10==0:self.emit('numeric',last=key,status=result['status'])
    assert proc.wait(timeout=30)==0,'Numeric worker failed; see numeric-stderr.log'
   finally:
    if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
 def report(self):
  cases=[dict(id=i,kind=k,status=s,seconds=t,result=json.loads(r),checked_at=at) for i,k,s,t,r,at in self.db.execute('select * from cases order by checked_at,id')]
  failures=[c for c in cases if c['status']!='pass'];data=dict(at=stamp(),scope='Local application robustness, not a new financial-source certification',identity=self.identity,completed=True,counts=dict(total=len(cases),passed=len(cases)-len(failures),failed=len(failures)),limitations=['Browser regression tests use isolated temporary Chrome contexts.','Finite deterministic scenario matrix, not all possible combinations of filters.','Load bounded to 4 parallel clients on the local machine; no production capacity claim.','SQL is a comparison reference, not an independent verification of every published source.','No destructive shutdown of Docker, operating system or service.','No AI call, RunPod job or vector re-encoding.'],cases=cases)
  save(self.out/'report.json',data)
  with (self.out/'anomalies.csv').open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f,delimiter=';');w.writerow(['Scénario','Type','Erreur','Durée (s)']);w.writerows((c['id'],c['kind'],c['result'].get('error',''),round(c['seconds'],3)) for c in failures)
  esc=html.escape
  rows=''.join('<tr><td>'+esc(c['id'])+'</td><td>'+('Réussi' if c['status']=='pass' else 'À examiner')+'</td><td>'+str(round(c['seconds'],2))+'</td><td><pre>'+esc(json.dumps(c['result'],ensure_ascii=False,indent=2))+'</pre></td></tr>' for c in cases)
  page='<!doctype html><html lang="fr"><meta charset="utf-8"><title>Nos Deniers — Test de solidité</title><style>body{font:16px system-ui;max-width:1300px;margin:40px auto;color:#173a52}h1{color:#101d40}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd6de;padding:10px;vertical-align:top}th{background:#edf4fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px monospace}summary{cursor:pointer}strong{color:#112343}</style><h1>Nos Deniers — Test de solidité du site</h1><p>'+esc(data['at'])+'</p><p><strong>'+str(len(cases))+' scénarios : '+str(len(cases)-len(failures))+' réussis, '+str(len(failures))+' à examiner.</strong></p><p>Site local uniquement. La base sert de référence pour les résultats ; ce rapport ne certifie pas à nouveau chaque document budgétaire.</p><p>Reprise après coupure : relancer le même lanceur. Les scénarios déjà enregistrés sont conservés. Aucune requête vers une IA ou RunPod.</p><h2>Anomalies</h2>'+(''.join('<p><b>'+esc(c['id'])+'</b> — '+esc(c['result'].get('error',''))+'</p>' for c in failures) or '<p>Aucune anomalie détectée dans les scénarios exécutés.</p>')+'<details><summary>Tous les contrôles et leurs résultats</summary><table><tr><th>Scénario</th><th>État</th><th>Secondes</th><th>Preuve</th></tr>'+rows+'</table></details></html>'
  (self.out/'rapport.html').write_text(page,'utf-8');self.emit('complete',passed=len(cases)-len(failures),failed=len(failures));return data
 def run(self):
  self.emit('starting_or_resuming')
  for route in ['/healthz','/readyz','/api/bootstrap','/','/assets/explorer.js','/assets/explorer.css','/api/semantic-search/status']:
   self.case('route:'+route,'HTTP',lambda r=route:self.basic(r))
  self.numeric()
  for y in range(2017,2027):
   for budget in ('BG','BA','CAS','CCF'):
    for measure in ('AE','CP'):
     p=dict(start=y,end=y,budget=budget,measure=measure);self.case('annual:'+query(p),'navigation_sql',lambda p=p:self.check_tree(p))
  for (budget,mission),year in sorted(self.scopes.items()):
   for measure in ('AE','CP'):
    p=dict(start=year,end=year,budget=budget,measure=measure,scope=mission);self.case('mission:'+query(p),'navigation_sql',lambda p=p:self.check_tree(p))
  programmes={}
  for y,s,m,b,mission,program,n in self.ref['rows']:
   if y==2026 and mission=='M26985a5788':mission='MB'
   key=(b,mission+'/'+program);programmes[key]=max(y,programmes.get(key,0))
  candidates=sorted(programmes)
  if not self.args.full_tree:candidates=sorted(set(candidates[::max(1,len(candidates)//16)])|{k for k in candidates if k[1] in ('TA/174','TA/345','TA/235','VA/135','PR/362')})
  for b,scope in candidates:
   p=dict(start=programmes[(b,scope)],end=programmes[(b,scope)],budget=b,measure='CP',scope=scope);self.case('programme:'+query(p),'navigation_details',lambda p=p:self.check_tree(p))
  for budget,scope in [('BG',''),('BG','TA'),('BG','TA/174'),('CAS',''),('BA',''),('CCF','')]:
   for measure in ('AE','CP'):
    p=dict(start=2017,end=2026,budget=budget,scope=scope,measure=measure)
    self.case('invariants:'+query(p),'filters',lambda p=p:self.invariants(p))
    narrow=p|dict(start=2023,end=2025);self.case('exports:'+query(narrow),'exports',lambda p=narrow:self.roundtrip(p))
  for mode in ('only','without'):
   p=dict(start=2020,end=2026,budget='BG',scope='TA' if mode=='without' else '',measure='CP',topic='maprimerenov',topic_mode=mode);self.case('mpr-exports:'+mode,'exports',lambda p=p:self.roundtrip(p))
  for endpoint in ('events','reserves','rap-movements'):
   for measure in ('AE','CP'):
    route='/api/'+endpoint+'?'+query(dict(start=2017,end=2026,budget='BG',scope='TA',measure=measure));self.case(route,'documented_management',lambda r=route:self.basic(r))
  for qs in ['start=oops','start=2016','end=2027','start=2025&end=2020','measure=XYZ','budget=UNKNOWN','scope=..%2F','exclude=%7B%7D','exclude=not-json','topic=wrong','base=2026','denominator=invalid',query(dict(exclude=['TA']*101))]:
   self.case('invalid:'+qs,'invalid_input',lambda qs=qs:self.basic('/api/explorer?'+qs,400))
  for route,expected in [('/api/download/does-not-exist',400),('/api/nonexistent',404),('/not-found',404)]:
   self.case('unknown:'+route,'invalid_input',lambda r=route,code=expected:self.basic(r,code))
  self.case('HEAD','HTTP',lambda:self.basic('/healthz',200,'HEAD'))
  for name in ['exclusion-restore.cjs','rap-refresh-state.cjs','rap-date-coverage-state.cjs','rap-pagination-review.cjs','mpr-provenance.cjs']:
   self.case('javascript:'+name,'javascript_lifecycle',lambda n=name:self.node_test(n))
  for name in ['final-audit-ui.cjs','pilot-dossiers-ui.cjs']:
   self.case('browser:'+name,'browser',lambda n=name:self.node_test(n,True))
  if not self.args.no_load:
   for n in (1,2,4):
    self.case('concurrency:'+str(n),'bounded_load',lambda n=n:self.load(n))
    if self.db.execute("select status from cases where id=?",('concurrency:'+str(n),)).fetchone()[0]!='pass':break
  self.case('final_service','recovery',lambda:self.basic('/readyz'))
  def stable():
   current=sql_reference(self.args.container);assert current['sha256']==self.ref['sha256'],'SQL changed during campaign';assert all(sha(request(self.base,p)['body'])==v for p,v in self.assets.items()),'Application changed during campaign';return dict(sql_and_assets_unchanged=True)
  self.case('unchanged_site','identity',stable)
  return self.report()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-url',default='http://127.0.0.1:8552');p.add_argument('--container',default='lexmachine-budget-web-1');p.add_argument('--output',type=Path,default=ROOT/'reports/crash-test-site-20260924');p.add_argument('--node',type=Path,default=DEFAULT_NODE);p.add_argument('--full-tree',action='store_true');p.add_argument('--no-load',action='store_true');a=p.parse_args()
 try:result=Campaign(a).run();print(dump(result['counts']));return 0 if not result['counts']['failed'] else 2
 except KeyboardInterrupt:print('Interrupted. Completed checkpoints preserved.');return 130
if __name__=='__main__':sys.exit(main())
