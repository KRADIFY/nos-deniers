"""Read-only numeric oracle against the application's active Python code in Docker.
Run with python - from stdin; each output line is an independently resumable phase.
"""
import json,sqlite3,collections,hashlib,datetime,sys,traceback
from pathlib import Path
from decimal import Decimal,ROUND_HALF_UP
from budget_service import api,action_details,model,topics,reserves,rap_movements,events
SKIP=set(json.loads(sys.argv[1])) if len(sys.argv)>1 else set()

def emit(key,fn):
 if key in SKIP:return
 try:result=fn();status='pass'
 except Exception as e:result=dict(error=str(e),traceback=traceback.format_exc());status='failure'
 print(json.dumps(dict(id=key,kind='all_display_amounts',status=status,result=result),ensure_ascii=False),flush=True)

def cents(item):return item['cents'] if 'cents' in item else item['euros']*100

db=api.connect();meta=api.metadata(db);indices={int(k):v for k,v in meta['indices'].items()}
groups=action_details.registry()[0]['groups'];issues=collections.Counter();known=meta.get('issues',[])
source_map={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')};source_map.update({s['id']:s for s in topics.sources()+events.sources(api.DATA)})
checked_sources={}
def check_source(sid,expected=None):
 src=source_map[sid];p=(api.DATA/src['path']).resolve();assert p.is_relative_to(api.DATA.resolve())
 if sid not in checked_sources:
  with p.open('rb') as f:checked_sources[sid]=hashlib.file_digest(f,'sha256').hexdigest()
 assert checked_sources[sid]==src['sha256'] and (expected is None or expected==src['sha256'])
 return src

def source_check():
 used={r[0] for r in db.execute('select distinct source from facts')}
 for sid in used:check_source(sid)
 return dict(canonical_facts=db.execute('select count(*) from facts').fetchone()[0],source_files_verified=len(used),known_source_disagreements=known,source_disagreements_not_automatically_resolved=True)
emit('numeric:source-bindings',source_check)

def registries():
 from budget_service.audit_registries import run
 result=run(db,check_source);return result|dict(source_files_verified=len(checked_sources))
emit('numeric:all-registries',registries)

def bucket(year,measure,budget):
 p=api.parameters(dict(start=[str(year)],end=[str(year)],measure=[measure],budget=[budget]));actual_rows=api.selected_records(db,p)
 originals=[dict(r) for r in db.execute('select * from facts where year=? and measure=? and budget=?',(year,measure,budget))]
 expected=collections.defaultdict(int);rows_by_stage=collections.defaultdict(list);programs=collections.defaultdict(set)
 for r in actual_rows:rows_by_stage[r['stage']].append(r)
 for r in originals:
  mission='MB' if year==2026 and r['mission']=='M26985a5788' else r['mission']
  parts=[x for x in (mission,r['program'],r['action'],r['subaction']) if x]
  for n in range(len(parts)+1):expected[(r['stage'],'/'.join(parts[:n]))]+=r['cents']
 blocked=set();derived=0;review_groups=[]
 for g in groups:
  if (g['year'],g['measure'],g['budget'])!=(year,measure,budget):continue
  path=g['mission']+'/'+g['program'];stage=g['stage'];review=bool(g.get('review_required'));check_source(g['source'],g['sha256'])
  if review:review_groups.append(dict(year=year,budget=budget,measure=measure,program=g['program'],stage=stage,difference_cents=g.get('reconciliation',{}).get('difference_cents')))
  for a in g['actions']:
   key=(stage,path+'/'+a['code'])
   if review and not action_details.published_disagreement(g):blocked.add(key)
   else:expected[key]=cents(a);derived+=1
   for s in a.get('subactions',[]):
    child=(stage,key[1]+'/'+s['code'])
    if (review and not action_details.published_disagreement(g)) or a.get('subactions_review',{}).get('status')=='review_required':blocked.add(child)
    else:expected[child]=cents(s);derived+=1
 results=[];comparisons=inflation=0;errors=[]
 for stage,scope in sorted(set(expected)|blocked):
  # All source rows of the given year/stage remain available to the actual selection engine.
  got=api.cell(rows_by_stage[stage],scope,year,stage,p,indices,rows_by_stage[stage])
  if (stage,scope) in blocked:
   if got['value'] is not None:errors.append(dict(scope=scope,stage=stage,problem='Unreviewed detail exposed',actual=got.get('nominal_cents')))
   continue
  wanted=expected[(stage,scope)]
  if got.get('nominal_cents')!=wanted:errors.append(dict(scope=scope,stage=stage,problem='Displayed cents differ from SQL/registered source',actual=got.get('nominal_cents'),expected=wanted,status=got['status']))
  comparisons+=1
  for base in range(2017,2026):
   exact=None if year not in indices or base not in indices else int((Decimal(wanted)*Decimal(str(indices[base]))/Decimal(str(indices[year]))).quantize(Decimal(1),rounding=ROUND_HALF_UP))
   actual=model.constant_cents(wanted,year,base,indices)
   if actual!=exact:errors.append(dict(scope=scope,stage=stage,base=base,problem='Inflation formula mismatch',actual=actual,expected=exact))
   inflation+=1
 if errors:raise ValueError(json.dumps(dict(year=year,measure=measure,budget=budget,checks=comparisons,errors=errors[:100],error_count=len(errors)),ensure_ascii=False))
 return dict(year=year,measure=measure,budget=budget,canonical_rows=len(originals),display_cells=comparisons,derived_action_subaction_cells=derived,blocked_details_verified=len(blocked),inflation_calculations=inflation,source_review_groups=review_groups)
for year in range(2017,2027):
 for budget in ('BG','BA','CAS','CCF'):
  for measure in ('AE','CP'):emit(f'numeric:{year}:{budget}:{measure}',lambda y=year,b=budget,m=measure:bucket(y,m,b))
def mpr():
 reg=topics.registry();count=hidden=converted=0;facts=reg['facts']
 for r in facts:
  check_source(r['source']);assert isinstance(r['cents'],int) and r['page']>0
 scopes={''}|{c['path'] for c in reg['carriers']}|{'/'.join(r[k] for k in ('mission','program','action','subaction') if r[k]) for r in facts}
 for year in range(2020,2027):
  for measure in ('AE','CP'):
   p=api.parameters(dict(start=[str(year)],end=[str(year)],measure=[measure],topic=['maprimerenov']))
   for stage in model.STAGES:
    for scope in scopes:
     relevant=[r for r in facts if (r['year'],r['stage'],r['measure'])==(year,stage,measure) and (not scope or '/'.join(r[k] for k in ('mission','program','action','subaction') if r[k])==scope or '/'.join(r[k] for k in ('mission','program','action','subaction') if r[k]).startswith(scope+'/'))]
     got=topics.subset(scope,year,stage,p,indices)
     if got['value'] is None:
      assert got.get('reason');hidden+=1;continue
     wanted=sum(r['cents'] for r in relevant);assert got['nominal_cents']==wanted,(year,measure,stage,scope,got,wanted)
     for base in range(2017,2026):
      real=topics.subset(scope,year,stage,p|dict(constant=True,base=base),indices)
      expected=None if year not in indices else (Decimal(wanted)*Decimal(str(indices[base]))/Decimal(str(indices[year]))).quantize(Decimal(1),rounding=ROUND_HALF_UP)/100
      assert real['value'] is None if expected is None else Decimal(str(real['value']))==expected
      converted+=1
     count+=1
 return dict(registered_facts=len(facts),scopes=len(scopes),available_cells_checked=count,unavailable_cells_with_explanation=hidden,inflation_calculations=converted,qualification='Checks published values; does not assert that unavailable data do not exist elsewhere')
emit('numeric:maprimerenov',mpr)

db.close()
