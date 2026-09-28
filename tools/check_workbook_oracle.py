"""Independent auditor arithmetic against the prepared site API."""
import json,sys,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/integration-classeurs-20260928'
sys.path.insert(0,str(ROOT/'auditeur-independant'))
from prepare_reference import prepare
from oracle import Reference,compare_cells
folder=OUT/'independent-reference-final'
if not folder.exists():prepare(OUT/'data/derived/budget.sqlite',ROOT/'budget_service/data',folder)
ref=Reference(folder);errors=[];count=0;scenarios=0
for budget in ('BG','BA','CAS','CCF'):
 for measure in ('AE','CP'):
  p=dict(start=2017,end=2026,budget=budget,measure=measure,scope='',exclude=[],constant=False,base=2025,topic='',topic_mode='only',denominator='LFI')
  query=dict(p,exclude='[]',constant='0')
  data=json.load(urllib.request.urlopen('http://127.0.0.1:8552/api/explorer?'+urllib.parse.urlencode(query),timeout=90))
  result=compare_cells(ref,p,data);errors.extend(result['errors']);count+=result['amounts'];scenarios+=1
report=dict(passed=not errors,scenarios=scenarios,numeric_cells=count,errors=errors)
(OUT/'independent-oracle.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False)[:3500]);assert not errors
