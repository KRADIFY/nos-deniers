"""Extract reviewed Ecology action tables without changing canonical facts."""
import hashlib,json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/actions-ecologie-20260910'
LABELS={
 '113':{'01':'Sites, paysages, publicité','02':'Innovation, territorialisation et contentieux','07':'Gestion des milieux et biodiversité'},
 '159':{'10':'Gouvernance, évaluation, études et prospective en matière de développement durable',
        '11':'Etudes et expertise en matière de développement durable','12':'Information géographique et cartographique','13':'Météorologie'},
 '205':{'01':'Surveillance et sûreté maritimes','02':'Emplois et formations maritimes',
        '03':'Innovation et flotte de commerce','04':'Action interministérielle de la mer',
        '05':"Soutien et systèmes d'information",'07':'Pêche et aquaculture','08':'Planification et économie bleue'},
 '380':{'01':'Performance environnementale','02':'Adaptation des territoires au changement climatique',
        '03':'Amélioration du cadre de vie'},
 '203':{'01':'Routes - Développement','04':'Routes - Entretien','41':'Ferroviaire','42':'Voies navigables',
        '43':'Ports','44':'Transports collectifs','45':'Transports combinés','47':'Fonctions support',
        '50':'Transport routier','51':'Sécurité ferroviaire','52':'Transport aérien',
        '53':"Dotation exceptionnelle à l'AFITF"}}
PAGES={'113':{2023:171,2024:184,2025:180},'159':{2023:282,2024:281,2025:269},
       '205':{2023:127,2024:135,2025:129},'380':{2023:590,2024:600,2025:580},
       '203':{2023:45,2024:44,2025:45}}
SOURCE={2023:'c793d7737895c135ad70',2024:'113330a8d3bb90c96604',2025:'06557292eccf98885e32'}


def numbers(line):
 return [int(s.replace(' ','')) for s in re.split(r'\s{2,}',line.strip()) if re.fullmatch(r'-?\d[\d ]*',s)]


def read_parents():
 """Refresh the exact original rows through the read-only Docker data mount."""
 query="""import json,sqlite3
c=sqlite3.connect('file:/data/derived/budget.sqlite?mode=ro',uri=True)
c.row_factory=sqlite3.Row
rows=c.execute("select * from facts where budget='BG' and mission='TA' and program in ('113','159','205','380','203') and year between 2023 and 2025 and stage in ('LFI','EXEC') order by program,year,measure,stage").fetchall()
print(json.dumps([dict(r) for r in rows],ensure_ascii=False))
"""
 raw=subprocess.check_output(['docker','exec','lexmachine-budget-web-1','python','-c',query],text=True,encoding='utf-8')
 parents=json.loads(raw)
 assert len(parents)==60,len(parents)
 assert all(not r['action'] and not r['subaction'] and r['title']=='HT2' for r in parents)
 return parents


def measure_lines(pages,first,year,measure):
 """Keep physical pages and stop at this measure's first consumption total.

 The following page may already contain last year's repeated tables. Never let
 those repeated rows enter the current year's actions or reconciliation.
 """
 heading=rf'^{year} / '+('AUTORISATIONS D.ENGAGEMENT' if measure=='AE' else 'CR[ÉE]DITS DE PAIEMENT')+r'\s*$'
 selected=[];started=False
 for number in range(first,min(first+3,len(pages)+1)):
  for line in pages[number-1].splitlines():
   if not started:
    if re.match(heading,line.strip()):started=True
    continue
   if re.match(r'^\d{4} / (?:AUTORISATIONS|CR[ÉE]DITS|PR[ÉE]SENTATION)',line.strip()):
    raise AssertionError(('Missing consumption total before another table',year,measure,number,line))
   selected.append((number,line))
   if line.strip().startswith('Total des '+measure) and 'consomm' in line:
    return selected
 raise AssertionError(('Incomplete table',year,measure,first))


def original_values(group):
 """Ignore only new citation metadata when checking the existing 24 groups."""
 result={k:v for k,v in group.items() if k!='total_page'}
 result['actions']=[{k:v for k,v in a.items() if k!='page'} for a in group['actions']]
 return result


def main():
 target=ROOT/'budget_service/data/actions-ecologie.json'
 previous=json.loads(target.read_text(encoding='utf-8'))['groups'] if target.exists() else []
 parents=read_parents()
 refs=json.loads((ROOT/'reports/actions-p174-20260910/reference.json').read_text(encoding='utf-8'))['sources']
 inv=json.loads((ROOT/'reports/reserves-et-consignes-20260909/rap-reserves-pages.json').read_text(encoding='utf-8'))
 groups=[];gaps=[];rendered=set()
 for program,years in PAGES.items():
  for year,page in years.items():
   pdf=Path(next(d['path'] for d in inv if d['year']==year))
   assert hashlib.sha256(pdf.read_bytes()).hexdigest()==refs[SOURCE[year]]['sha256']
   pages=(ROOT/f'reports/reserves-et-consignes-20260909/rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')
   used_pages=set()
   for measure in ('AE','CP'):
    lines=measure_lines(pages,page,year,measure);lfi=[];executed=[]
    used_pages.update(number for number,_ in lines)
    for i,(number,line) in enumerate(lines):
     m=re.match(r'^\s*(\d{2}) – ',line)
     if not m:continue
     code=m[1];assert code in LABELS[program]
     actual_page,actual_line=lines[i+1]
     forecast,actual=numbers(line),numbers(actual_line)
     assert len(forecast)>=2 and len(actual)>=1,(program,year,measure,code)
     lfi.append(dict(code=code,label=LABELS[program][code],euros=forecast[-2],page=number))
     executed.append(dict(code=code,label=LABELS[program][code],euros=actual[-1],page=actual_page))
    assert [a['code'] for a in lfi]==list(LABELS[program]),(program,year,measure)
    for stage,actions in [('LFI',lfi),('EXEC',executed)]:
     found=[r for r in parents if (r['program'],r['year'],r['measure'],r['stage'])==(program,year,measure,stage)]
     assert len(found)==1 and not found[0]['action']
     parent=found[0]
     matches=[(number,line) for number,line in lines if line.strip().startswith('Total des '+measure) and ('en LFI' in line if stage=='LFI' else 'consomm' in line)]
     assert len(matches)==1,(year,program,stage,measure)
     total_page,total_line=matches[0]
     totals=numbers(total_line)
     published=totals[-2] if stage=='LFI' else totals[-1]
     delta=sum(a['euros']*100 for a in actions)-parent['cents']
     group=dict(year=year,stage=stage,measure=measure,budget='BG',mission='TA',program=program,
                source=SOURCE[year],sha256=refs[SOURCE[year]]['sha256'],page=page,total_page=total_page,parent=parent,
                published_total_euros=published,action_sum_minus_parent_cents=delta,actions=actions)
     if (program,year,measure,stage)==('203',2023,'AE','EXEC'):
      assert published==8113476696 and parent['cents']==811347669000 and delta==600
      gaps.append(dict(group,status='excluded',reason_code='rap_csv_total_mismatch',
                       published_total_minus_parent_cents=600,
                       reason="Le total consommé AE 2023 du P203 est de 8 113 476 696 € dans le RAP, contre 8 113 476 690 € dans l’annexe CSV (valeur brute vérifiée). L’écart de 6 € porte sur les totaux publiés, pas seulement sur les arrondis des actions. Le groupe est exclu du registre ; le total canonique reste inchangé."))
      continue
     assert abs(delta)<=min(1000, len(actions)*50 if stage=='EXEC' else 0),(year,program,stage,measure,delta)
     assert abs(published*100-parent['cents'])<=(50 if stage=='EXEC' else 0),(year,program,stage,measure)
     groups.append(group)
   for number in sorted(used_pages):
    if (year,number) in rendered:continue
    (REPORT/f'rap-{year}-p{number}.txt').write_text(pages[number-1],encoding='utf-8')
    exe=Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
    subprocess.run([str(exe),'-f',str(number),'-singlefile','-r','125','-png',str(pdf),str(REPORT/f'rap-{year}-p{number}')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    rendered.add((year,number))
 for old in previous:
  if old['program'] not in ('113','159'):continue
  found=[g for g in groups if (g['program'],g['year'],g['stage'],g['measure'])==(old['program'],old['year'],old['stage'],old['measure'])]
  assert len(found)==1 and original_values(found[0])==original_values(old),('Changed existing group',old['program'],old['year'],old['stage'],old['measure'])
 assert len(groups)==59 and len(gaps)==1
 data=dict(updated_at='2026-09-10',coverage='P113, P159, P205 et P380 : LFI/consommé, AE/CP, 2023–2025 ; P203 : mêmes séries sauf consommé AE 2023 (divergence RAP/CSV de 6 €) ; aucune sous-action.',groups=groups)
 (REPORT/'parents.json').write_text(json.dumps(parents,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (REPORT/'reconciliation.json').write_text(json.dumps([{k:g[k] for k in ('year','program','measure','stage','page','total_page','published_total_euros','action_sum_minus_parent_cents')} for g in groups],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (REPORT/'gaps.json').write_text(json.dumps(gaps,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (REPORT/'rendered-pages.json').write_text(json.dumps([dict(year=y,page=p,path=str(REPORT/f'rap-{y}-p{p}.png')) for y,p in sorted(rendered)],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(len(groups),'groupes ;',sum(len(g['actions']) for g in groups),'observations ;',hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
