"""Inject errors into in-memory copies of real reference cells, never the database."""
import argparse,copy,json
from pathlib import Path
from coverage import compare_rows,numeric_cells,save
from oracle import Reference

def run(reference,coverage,out):
    ref=Reference(reference)
    facts=[dict(year=y,budget=b,program=p.split('/')[1],measure=m,stage=s,cents=c) for (b,m,y,s,p),c in ref.amounts.items() if p.count('/')==1]
    bykey={(f['year'],f['budget'],f['program'],f['measure'],f['stage']):f for f in facts}
    cells=json.loads((Path(coverage)/'cells.json').read_text('utf-8'))
    chosen=next(c for c in cells if c['status']=='matched' and c['expected_cents']!=0 and c['stage']=='REPORT_ENTRANT')
    row=dict(source=chosen['source'],sha256='',year=chosen['year'],budget=chosen['budget'],program=chosen['program'],measure=chosen['measure'],opening_gap_cents=0,closing_gap_cents=0,cells={chosen['stage']:dict(cents=chosen['expected_cents'],page=chosen['page'],raw=chosen['raw'],bbox=chosen['bbox'])})
    key=(row['year'],row['budget'],row['program'],row['measure'],chosen['stage']);original=bykey[key]
    tests=[]
    def check(name,changed,testrow=None):
        result=compare_rows([testrow or row],changed,[]);tests.append(dict(test=name,detected=any(r['status']!='matched' for r in result),result=result))
    tests.append(dict(test='Cellule témoin intacte',detected=compare_rows([row],[original],[])[0]['status']=='matched'))
    check('Ligne supprimée',[])
    check('AE/CP inversés',[dict(original,measure='CP' if original['measure']=='AE' else 'AE')])
    check('Mauvaise année',[dict(original,year=original['year']+1)])
    check('Mauvaise colonne',[dict(original,stage='EXEC')])
    check('Un centime ajouté',[dict(original,cents=original['cents']+1)])
    check('Ligne dupliquée',[original,dict(original)])
    blank=copy.deepcopy(row);blank['cells'][chosen['stage']].update(cents=None,raw='');check('Blanc remplacé par zéro',[dict(original,cents=0)],blank)
    # Entire published table omitted from the data, with source inventory retained.
    tablecells=[c for c in cells if (c['year'],c['budget'],c['program'],c['measure'])==key[:4] and c['status']=='matched']
    whole=copy.deepcopy(row);whole['cells']={c['stage']:dict(cents=c['expected_cents'],page=c['page'],raw=c['raw'],bbox=c['bbox']) for c in tablecells};check('Tableau entier oublié',[],whole)
    try:numeric_cells([],anchors=[100]);detected=False
    except ValueError:detected=True
    tests.append(dict(test='Cellule PDF vide sans zéro imprimé',detected=detected))
    report=dict(passed=all(t['detected'] for t in tests),tests=len(tests),results=tests,source_modified=False,method='Altérations de copies en mémoire de cellules réelles ; aucune écriture dans la référence ou le site.')
    save(out,report);return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',required=True);p.add_argument('--coverage',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=run(a.reference,a.coverage,a.output);print(json.dumps({k:v for k,v in r.items() if k!='results'},ensure_ascii=False));raise SystemExit(0 if r['passed'] else 1)
