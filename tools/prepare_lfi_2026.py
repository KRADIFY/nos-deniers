"""Prepare a checked LFI 2026 import from the archived PISTE law and decree."""
from pathlib import Path
import json,sqlite3,hashlib,sys,collections
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from budget_service.legal_tables import tables
from budget_service.model import norm,cents
X=R/'vectorisation-nos-deniers-20260909';B=R/'reports/developpement-20260909/lfi2026';B.mkdir(exist_ok=True)
manifest=json.loads((X/'_controle/textes-juridiques.json').read_text(encoding='utf-8'))['items']
for r in manifest:assert hashlib.sha256((X/r['path']).read_bytes()).hexdigest()==r['sha256']
law=tables((X/'textes-juridiques/JORFTEXT000053508155.html').read_text(encoding='utf-8'))
decree=tables((X/'textes-juridiques/JORFTEXT000053510204.html').read_text(encoding='utf-8'))
amount_tables=[(i,t) for i,t in enumerate(law) if t and len(t[0])==3 and norm(t[0][0])=='missionprogramme' and norm(t[0][1])=='autorisationsdengagement' and norm(t[0][2])=='creditsdepaiement']
assert len(amount_tables)==4
db=sqlite3.connect((X/'donnees-structurees/budget.sqlite').as_uri()+'?mode=ro',uri=True)
oldmissions=collections.defaultdict(set)
for b,label,mc in db.execute('select distinct budget,mission_label,mission from facts where year=2025'):oldmissions[(b,norm(label))].add(mc)
new_sources=[]
for r in manifest:
 path='public/legal/lfi2026/'+Path(r['path']).name
 new_sources.append(dict(r,path=path,id=hashlib.sha256(path.encode()).hexdigest()[:20],years_title=['2026'],role='official_document',imported=r['format']=='html' and '508155' in r['id'],original_export_path=r['path']))
source=next(r for r in new_sources if r['id'] and r['format']=='html' and '508155' in r['path'])
facts=[];checks=[];nodes=[];mapping=[]
for budget,(table_index,table),d in zip(['BG','BA','CAS','CCF'],amount_tables,decree[:4]):
    catalogue={};mission=None
    for line,row in enumerate(d[1:],2):
        assert len(row)==3
        if not row[1]:mission=row[0];catalogue[norm(mission)]=dict(kind='mission',label=mission,line=line)
        else:
            assert row[1].isdigit() and len(row[1])==3
            key=norm(row[0]);assert key not in catalogue,(budget,row[0])
            catalogue[key]=dict(kind='programme',label=row[0],program=row[1],mission=mission,line=line,authority=row[2])
    mission_codes={}
    for item in catalogue.values():
        if item['kind']=='mission':
            previous=oldmissions.get((budget,norm(item['label'])),set())
            mc=next(iter(previous)) if len(previous)==1 else 'M26'+hashlib.sha256((budget+item['label']).encode()).hexdigest()[:8]
            mission_codes[item['label']]=mc
            mapping.append(dict(budget=budget,mission=mc,label=item['label'],code_basis='Exact normalized mission label in 2025 nomenclature' if len(previous)==1 else 'Internal identifier; official mission code not supplied in legal table'))
    current=None;observed={}
    for line,row in enumerate(table[1:],2):
        assert len(row)==3,(table_index,line,row)
        key=norm(row[0])
        if key=='donttitre2':continue
        if key=='total':
            for measure,col in [('AE',1),('CP',2)]:checks.append(dict(budget=budget,path='',measure=measure,expected=cents(row[col]),actual=sum(r[14] for r in facts if r[2]==measure and r[3]==budget),table=table_index+1,line=line))
            continue
        item=catalogue.get(key);assert item,(budget,line,row[0])
        if item['kind']=='mission':
            current=item['label'];mc=mission_codes[current]
            observed[mc]=(cents(row[1]),cents(row[2]),line)
            continue
        assert current==item['mission'],(current,item)
        for measure,col in [('AE',1),('CP',2)]:
            amount=cents(row[col]);assert amount is not None,(line,row)
            facts.append((2026,'LFI',measure,budget,mc,current,item['program'],row[0],'','','','','','',amount,source['id'],line,f'Loi de finances 2026 · tableau {table_index+1} · ligne {line} · {measure}',0))
            nodes.append((2026,'LFI',measure,budget,mc+'/'+item['program'],'published',source['id'],line))
    for mc,(ae,cp,line) in observed.items():
        for measure,expected in [('AE',ae),('CP',cp)]:checks.append(dict(budget=budget,path=mc,measure=measure,expected=expected,actual=sum(r[14] for r in facts if r[2]==measure and r[3]==budget and r[4]==mc),table=table_index+1,line=line))
assert all(c['actual']==c['expected'] for c in checks),[c for c in checks if c['actual']!=c['expected']]
result=dict(facts=facts,sources=new_sources,checks=checks,published_nodes=nodes,mission_mapping=mapping,exclusions='États des recettes, autorisations de découvert et moyens globaux exclus des crédits AE/CP.')
(B/'plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(facts=len(facts),checks=len(checks),failures=0,internal_missions=[x for x in mapping if x['code_basis'].startswith('Internal')]),ensure_ascii=False))
