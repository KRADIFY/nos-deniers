"""Re-read the selected historical XLS action groups at source cent precision.

Only report candidates are written. The original workbooks and application data
remain untouched. xlrd is needed because the official sources use legacy XLS.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re,sqlite3
from collections import Counter
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT=ROOT/'reports/restore-20260910-actions-mpr/data'
DEFAULT_GROUPS=ROOT/'budget_service/data/actions-rap-historique.json'
DEFAULT_OUT=ROOT/'reports/historical-xls-actions-cents-20260923'

def cents(value):
    if value is None or value=='':
        return None
    if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):
        raise ValueError(f'Non-numeric monetary cell: {value!r}')
    decimal=Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError('Non-finite monetary cell')
    return int((decimal*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def colname(index):
    out='';index+=1
    while index:
        index,rem=divmod(index-1,26);out=chr(65+rem)+out
    return out

def code(value):
    return str(int(value)) if isinstance(value,(int,float)) else str(value).strip()

def cell_proof(book,sheet,row,col):
    cell=sheet.cell(row,col);raw=cell.value
    fmt=book.format_map[book.xf_list[cell.xf_index].format_key].format_str
    # These sources explicitly publish cents; retain the binary-read value too.
    if raw!='' and '#,##0.00' not in fmt:
        raise ValueError(f'Unexpected source precision: {sheet.name}!{colname(col)}{row+1}: {fmt}')
    amount=cents(raw)
    return dict(sheet=sheet.name,row=row+1,column=colname(col),column_index=col+1,
                cell=f'{colname(col)}{row+1}',raw_value=repr(raw),cell_type=cell.ctype,
                number_format=fmt,cents=amount)

def read_source(path,year):
    import xlrd
    book=xlrd.open_workbook(path,on_demand=True,formatting_info=True)
    sheet=book.sheet_by_name('Crédits')
    # Locate current-year consumption from its own heading, not previous-year/LFI.
    starts=[c for c in range(sheet.ncols) if str(sheet.cell_value(1,c)).strip()=='Consommation']
    columns={}
    for c in starts:
        end=next((n for n in range(c+1,sheet.ncols) if str(sheet.cell_value(1,n)).strip()),sheet.ncols)
        for j in range(c,end):
            for measure in ('AE','CP'):
                if str(sheet.cell_value(2,j)).strip()==f'{measure} {year}':
                    if measure in columns:raise ValueError('Ambiguous current-year consumption header')
                    columns[measure]=j
    if set(columns)!= {'AE','CP'}:raise ValueError('Missing current-year consumption columns')
    programs={};mission=mission_label='';program=None;action=None
    for row in range(3,sheet.nrows):
        kind=str(sheet.cell_value(row,0)).strip()
        if kind not in {'Mission','Programme','Action','Sous action'}:continue
        budget=str(sheet.cell_value(row,1)).strip();full_code=code(sheet.cell_value(row,2));label=' '.join(str(sheet.cell_value(row,3)).split())
        if kind=='Mission':mission=full_code;mission_label=label;program=None;action=None;continue
        proofs={m:cell_proof(book,sheet,row,c) for m,c in columns.items()}
        entry=dict(full_code=full_code,label=label,proofs=proofs)
        if kind=='Programme':
            key=(budget,mission,full_code)
            if key in programs:raise ValueError(f'Duplicate source programme {key}')
            program=dict(**entry,budget=budget,mission=mission,mission_label=mission_label,actions=[])
            programs[key]=program;action=None
        elif kind=='Action':
            if program is None or not full_code.startswith(program['full_code']+'-'):raise ValueError(f'Action outside programme: {full_code}')
            action=dict(**entry,code=full_code.split('-')[1],subactions=[]);program['actions'].append(action)
        else:
            if action is None or not full_code.startswith(action['full_code']+'-'):raise ValueError(f'Subaction outside action: {full_code}')
            action['subactions'].append(dict(**entry,code=full_code.split('-')[2]))
    header=dict(sheet=sheet.name,section_cell='Q2',section=str(sheet.cell_value(1,min(columns.values())-2)).strip(),columns={m:dict(cell=f'{colname(c)}3',label=str(sheet.cell_value(2,c)).strip(),column=colname(c)) for m,c in columns.items()},rows=sheet.nrows)
    book.release_resources()
    return programs,header

def location(proof):
    return {k:proof[k] for k in ('sheet','row','column')}

def reconcile(actual,published,count):
    difference=actual-published
    # Each source cell has cent precision; allow only its explicit rounding envelope.
    bound=(count+2)//2
    return dict(status='exact' if difference==0 else 'published_rounding_difference' if abs(difference)<=bound else 'review_required',difference_cents=difference,source_precision_cents=1,rounding_bound_cents=bound,automatic_limit_cents=min(bound,1000),materiality_bound_cents=1000,review_required=abs(difference)>bound,accepted=abs(difference)<=bound)

def build(input_path,source_root,out):
    out.mkdir(parents=True,exist_ok=True)
    payload=json.loads(input_path.read_text('utf8'));groups=payload['groups']
    db=sqlite3.connect(f'file:{(source_root/"derived/budget.sqlite").as_posix()}?mode=ro',uri=True)
    sources={};parsed={};proofs=[];diffs=[];checks=[];blanks=[];added=[];removed=[]
    for original in groups:
        sid=original['source'];year=original['year']
        if sid not in sources:
            meta=json.loads(db.execute('select data from sources where id=?',(sid,)).fetchone()[0]);path=source_root/meta['path'];sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if sha!=meta['sha256'] or sha!=original['sha256']:raise ValueError(f'Source SHA mismatch: {sid}')
            parsed[sid],header=read_source(path,year)
            sources[sid]=dict(id=sid,year=year,path=str(path),url=meta['url'],sha256=sha,format='xls',header=header)
    newgroups=[]
    for original in groups:
        g=copy.deepcopy(original);pcode=str(g.get('program') or g['parent']['program']);measure=g['measure'];key=(g['budget'],g['mission'],pcode);program=parsed[g['source']][key];proof=program['proofs'][measure]
        if proof['cents'] is None:raise ValueError('Programme total is blank')
        if proof['cents']!=g['parent']['cents']:raise ValueError(f'Programme/source reference mismatch: {g["year"]} {pcode} {measure}')
        identity=dict(year=g['year'],budget=g['budget'],mission=g['mission'],program=pcode,measure=measure)
        for k in ('page','total_page','reconciliation','action_reconciliation','reconciliation_note','published_total_minus_parent_cents','action_sum_minus_parent_cents'):g.pop(k,None)
        g.update(program=pcode,program_label=program['label'],mission_label=program['mission_label'],source_format='xls',source_kind='official_spreadsheet',source_precision='centime',published_total_cents=proof['cents'],published_total_euros=proof['cents']/100,source_location=location(proof),line=proof['row'],field=f'Crédits!{proof["cell"]} — Consommation {g["year"]} — {measure} total')
        # Keep the exact canonical parent object used by attach(); cell locators belong to the group/items.
        olditems={(a['code'],):a for a in original['actions']}
        for a in original['actions']:
            olditems.update({(a['code'],s['code']):s for s in a.get('subactions',[])})
        currentitems={};actions=[]
        proofs.append(dict(**identity,level='programme',source=g['source'],proof=proof))
        def convert(entry,parts):
            p=entry['proofs'][measure]
            if p['cents'] is None:
                blanks.append(dict(**identity,path=list(parts),source=g['source'],proof=p));return None
            item=dict(code=entry['code'],label=entry['label'],cents=p['cents'],euros=p['cents']/100,source=g['source'],source_format='xls',source_kind='official_spreadsheet',source_location=location(p),line=p['row'],field=f'Crédits!{p["cell"]} — Consommation {g["year"]} — {measure} total')
            currentitems[parts]=item;proofs.append(dict(**identity,level='action' if len(parts)==1 else 'subaction',path=list(parts),source=g['source'],proof=p))
            return item
        for a in program['actions']:
            item=convert(a,(a['code'],));children=[]
            for sub in a['subactions']:
                s=convert(sub,(a['code'],sub['code']))
                if s is not None:children.append(s)
            if item is None:
                if children:raise ValueError(f'Numeric children with blank action: {identity} {a["code"]}')
                continue
            if children:
                item['subactions']=children;subtotal=sum(c['cents'] for c in children);check=reconcile(subtotal,item['cents'],len(children));item['subaction_reconciliation']=check
                checks.append(dict(**identity,level='subactions',action=a['code'],source=g['source'],source_location=item['source_location'],child_count=len(children),child_sum_cents=subtotal,source_total_cents=item['cents'],**check))
            actions.append(item)
        for parts,old in olditems.items():
            new=currentitems.get(parts)
            if new is None:removed.append(dict(**identity,path=list(parts),old=old));continue
            oldcents=int(Decimal(str(old['euros']))*100)
            if oldcents!=new['cents']:diffs.append(dict(**identity,path=list(parts),old_cents=oldcents,new_cents=new['cents'],difference_cents=new['cents']-oldcents,source_location=new['source_location']))
        for parts,new in currentitems.items():
            if parts not in olditems:added.append(dict(**identity,path=list(parts),cents=new['cents'],source_location=new['source_location']))
        total=sum(a['cents'] for a in actions);check=reconcile(total,proof['cents'],len(actions))
        g.update(actions=actions,action_sum_minus_parent_cents=total-proof['cents'],published_total_minus_parent_cents=0,reconciliation=reconcile(proof['cents'],g['parent']['cents'],1),action_reconciliation=check,reconciliation_note='Montants relus dans les cellules XLS au centime publié ; sous-actions contrôlées séparément, sans les ajouter une seconde fois au programme.')
        checks.append(dict(**identity,level='actions',source=g['source'],source_location=g['source_location'],child_count=len(actions),child_sum_cents=total,source_total_cents=proof['cents'],**check));newgroups.append(g)
    payload.update(groups=newgroups,updated_at='2026-09-23',coverage='82 groupes RAP 2021–2022 sélectionnés dans le registre historique. Actions rapprochées des programmes ; sous-actions rapprochées de leur action, sans additionner deux niveaux.',note='Synthèses XLS officielles 2021–2022 relues au centime avec coordonnées de cellule ; candidats non promus automatiquement.')
    errors=[c for c in checks if c['review_required']]
    review=dict(version=1,input_path=str(input_path),input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),groups=len(groups),actions=sum(len(g['actions']) for g in newgroups),subactions=sum(len(a.get('subactions',[])) for g in newgroups for a in g['actions']),changed_monetary_items=len(diffs),added_items=len(added),removed_items=len(removed),blank_cells_omitted=len(blanks),checks=len(checks),check_status_counts=dict(Counter(c['status'] for c in checks)),source_units='EUR',candidate_storage_units='EUR_CENTS',precision_rule='Valeur numérique XLS arrondie au centime par Decimal(str(value)), ROUND_HALF_UP ; aucun passage par des euros entiers.',sources=sources,monetary_changes=diffs,added=added,removed=removed,blank_cells=blanks,validation=checks,errors=errors)
    (out/'actions-rap-historique-cents-candidates.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),'utf8')
    (out/'xls-actions-source-proofs.json').write_text(json.dumps(dict(sources=sources,records=proofs),ensure_ascii=False,indent=2),'utf8')
    (out/'xls-actions-cents-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:v for k,v in review.items() if k in ('groups','actions','subactions','changed_monetary_items','added_items','removed_items','blank_cells_omitted','checks','check_status_counts')},ensure_ascii=False))
    if removed or errors:raise SystemExit('Candidate review required: dropped items or hierarchy mismatch')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--groups',type=Path,default=DEFAULT_GROUPS);p.add_argument('--source-root',type=Path,default=DEFAULT_SOURCE_ROOT);p.add_argument('--output',type=Path,default=DEFAULT_OUT);args=p.parse_args();build(args.groups,args.source_root,args.output)
if __name__=='__main__':main()
