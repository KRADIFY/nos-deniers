from contextlib import closing
"""Evidence ledger for zero/blank meaning. Never changes a budget amount.

Independent source reader: a blank, dash or missing coordinate is never inferred
to mean zero. A PDF page number is a citation, not proof of a particular cell.
"""
import collections,csv,hashlib,html,json,re,sqlite3,unicodedata
from decimal import Decimal,InvalidOperation
from pathlib import Path
from oracle import digest,nodepath
from document_zeros import DocumentProofs

LABELS={
 'source_zero':'Zéro explicite dans la cellule source',
 'calculated_zero':'Zéro obtenu par addition de cellules sources',
 'source_blank':'Cellule source vide : sens non établi',
 'source_dash':'Tiret dans la source : sens non établi',
 'source_not_applicable':'Mention explicite « sans objet » dans la source',
 'nonzero_source':'La cellule source contient un montant non nul',
 'document_review_recorded':'Zéro documenté lors d’une relecture antérieure',
 'undetermined':'Sens non déterminé : vérification nécessaire',
 'excluded':'Zéro de calcul dû aux exclusions',
 'not_applicable':'Sans objet selon le périmètre documenté',
 'missing':'Montant absent de la base sur cette sélection',
 'missing_detail':'Détail insuffisant pour isoler le montant',
 'inflation_missing':'Montant connu, conversion par inflation indisponible',
 'referenced_zero':'Zéro de la référence, avec sources à examiner',
 'unproven_zero':'Zéro sans observation monétaire ni preuve attachée',
 'computed_zero':'Solde nul calculé à partir des montants de référence',
}
def key(s):
    s=re.sub(r'(?<![A-Za-z0-9])[Nn]\s*[−-]\s*1','nminus1',str(s));s=re.sub(r'(?<![A-Za-z0-9])[Nn]\s*\+\s*1','nplus1',s)
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def meaning(raw):
    if raw is None or str(raw).strip()=='':return 'source_blank',None
    s=str(raw).strip()
    if s in ('-','—','–'):return 'source_dash',None
    if s.casefold() in ('sans objet','s.o.','s/o','non applicable','not applicable'):return 'source_not_applicable',None
    s=re.sub(r'\s','',s).replace(',','.')
    if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
    try:
        value=Decimal(s)
        if not value.is_finite():return 'undetermined',None
        return ('source_zero' if value==0 else 'nonzero_source'),value
    except InvalidOperation:return 'undetermined',None

class Reader:
    def __init__(self,root):
        self.root=Path(root).resolve() if root else None;self.cache={};self.documents=DocumentProofs()
    def source(self,s):
        sid=s['id']
        if sid in self.cache:return self.cache[sid]
        try:
            if self.root is None:raise ValueError('Dossier des documents sources non monté.')
            p=(self.root/s['path']).resolve()
            if not p.is_relative_to(self.root):raise ValueError('Chemin de source hors du corpus.')
            if not p.is_file():raise ValueError('Copie source non accessible dans ce contrôle.')
            if not s.get('sha256') or digest(p)!=s['sha256']:raise ValueError('Empreinte de la source absente ou différente.')
            fmt=s.get('format')
            if fmt=='csv':
                with p.open(encoding=s.get('encoding') or 'utf-8-sig',newline='') as f:rows=list(csv.reader(f,delimiter=s.get('delimiter') or ';'))
                result={'sheets':{'':rows},'default':''}
            elif fmt=='xls':
                import xlrd
                book=xlrd.open_workbook(str(p),on_demand=True)
                result={'sheets':{sh.name:[sh.row_values(i) for i in range(sh.nrows)] for sh in book.sheets()},'default':book.sheet_names()[0]}
                book.release_resources()
            else:result={'document_only':True,'path':p}
        except Exception as e:result={'error':str(e)}
        self.cache[sid]=result;return result
    def inspect(self,f,s):
        data=self.source(s)
        if 'error' in data:return dict(status='undetermined',reason=data['error'])
        if data.get('document_only'):
            reviewed=self.documents.inspect(f,s,data['path'])
            if reviewed is not None:return reviewed
            note=f.get('field','')
            if 'zéro explicitement publié' in note.lower():
                return dict(status='document_review_recorded',reason='La provenance conserve une relecture explicite du zéro et sa page. Cette campagne ne relit pas automatiquement la cellule PDF.',raw=note)
            return dict(status='undetermined',reason='Document non tabulaire ou coordonnées de cellule insuffisantes pour trancher automatiquement.',raw=note)
        field=f.get('field','');line=f.get('line');sheet=data['default'];column=None
        coord=re.match(r"'?(.+?)'?!(\$?[A-Z]+)\$?(\d+)",field)
        if coord:
            sheet=coord[1];line=int(coord[3]);column=0
            for c in coord[2].replace('$',''):column=column*26+ord(c)-64
            column-=1
        rows=data['sheets'].get(sheet)
        if rows is None or not isinstance(line,int) or not 1<=line<=len(rows):return dict(status='undetermined',reason='Ligne ou feuille source non localisable sans ambiguïté.')
        row=rows[line-1];headers=rows[0] if rows else [];wanted=[]
        if column is None:
            # Some historical files begin with a GESTION/year row, before the header.
            candidates=[h for h in rows[:min(line-1,20)] if any(key(v)==key(field) for v in h)]
            signatures={tuple(key(v) for v in h) for h in candidates}
            if len(signatures)==1:headers=candidates[0]
        if column is not None:wanted=[column]
        else:
            exact=[i for i,h in enumerate(headers) if key(h)==key(field)]
            if len(exact)==1:wanted=exact
            elif ' + ' in field:
                for term in field.split(' + '):
                    cols=[i for i,h in enumerate(headers) if key(h)==key(term)]
                    if len(cols)!=1:return dict(status='undetermined',reason='Colonne de la formule source absente ou en double.')
                    wanted+=cols
            else:return dict(status='undetermined',reason='Colonne source absente ou en double : '+field)
        if any(i>=len(row) for i in wanted):return dict(status='undetermined',reason='La ligne source est plus courte que l’en-tête.')
        raw=[row[i] for i in wanted];parts=[meaning(v) for v in raw]
        proof=dict(raw=raw,location=dict(sheet=sheet,row=line,columns=[i+1 for i in wanted]))
        if all(v is not None for _,v in parts):
            total=sum(v for _,v in parts)
            status=('source_zero' if len(raw)==1 else 'calculated_zero') if total==0 else 'nonzero_source'
            return dict(proof,status=status,reason='Valeur relue dans les coordonnées sources, fichier vérifié par empreinte.',source_sum=str(total))
        priority=['source_blank','source_dash','source_not_applicable','undetermined']
        status=next(x for x in priority if any(t==x for t,_ in parts))
        return dict(proof,status=status,reason='Cette notation source ne suffit pas à justifier le zéro enregistré dans la base.')

def classify_cell(ref,p,year,stage,path,c):
    """Explain API semantics without pretending to have re-read the original PDF."""
    value=c.get('nominal_cents')
    if value is None and c.get('nominal') is not None:value=round(c['nominal']*100)
    if value not in (None,0) and c.get('value') is not None:return None
    status=c.get('status')
    if status=='not_applicable':kind='not_applicable'
    elif status=='inflation_missing' and value is not None:kind='inflation_missing'
    elif value is None:kind='missing_detail' if status in ('detail_unavailable','topic_unavailable') else 'missing'
    elif status=='excluded':kind='excluded'
    elif p.get('topic') and not c.get('sources'):kind='unproven_zero'
    elif p.get('exclude') or (p.get('topic') and p.get('topic_mode')=='without'):kind='computed_zero'
    else:kind='referenced_zero'
    return dict(status=kind,label=LABELS[kind],reason=c.get('reason',''),source_ids=c.get('sources',[]))

def source_ledger(ref,root,out):
    reader=Reader(root);items=[]
    for f in ref.rows:
        if f['cents']!=0:continue
        s=ref.sources[f['source']];result=reader.inspect(f,s)
        item={k:f[k] for k in ('budget','year','measure','stage','source','line','field','category','title')}
        item.update(path=nodepath(f),**result,label=LABELS[result['status']],source_title=s.get('title',''),source_url=s.get('url',''),sha256=s.get('sha256',''))
        items.append(item)
    # Registries remain distinct from original structured facts.
    for g in ref.groups:
        for a in g['actions']:
            for detail in [a]+a.get('subactions',[]):
                cents=detail.get('cents',detail.get('euros',0)*100)
                if cents!=0:continue
                sid=detail.get('source',g['source']);s=ref.sources[sid]
                loc=detail.get('source_location') or {};field=detail.get('field','')
                if loc.get('sheet') and loc.get('column') and loc.get('row'):field=f"{loc['sheet']}!{loc['column']}{loc['row']}"
                f=dict(field=field,line=detail.get('line',g.get('page')),source=sid)
                result=reader.inspect(f,s)
                items.append(dict(budget=g['budget'],year=g['year'],measure=g['measure'],stage=g['stage'],path=g['mission']+'/'+g['program']+'/'+a['code']+('/'+detail['code'] if detail is not a else ''),source=sid,line=f['line'],field=field,category='',title='',**result,label=LABELS[result['status']],source_title=s.get('title',''),source_url=s.get('url',''),sha256=s.get('sha256',''),registry=True))
    for f in ref.mpr['facts']:
        if f['cents']!=0:continue
        s=ref.sources[f['source']]
        items.append(dict(budget='BG',year=f['year'],measure=f['measure'],stage=f['stage'],path=nodepath(f),source=f['source'],line=f.get('page'),field=f.get('precision',''),status='document_review_recorded',label=LABELS['document_review_recorded'],reason='Observation monétaire nulle conservée dans le registre MaPrimeRénov’, avec référence de page. Cellule PDF à relire pour une confirmation indépendante.',source_title=s.get('title',''),source_url=s.get('url',''),sha256=s.get('sha256',''),registry=True))
    counts=dict(collections.Counter(i['status'] for i in items));out=Path(out)
    with closing(sqlite3.connect(out/'zeros-sources.sqlite')) as db, db:
        db.execute('create table if not exists items(status text, search text, data text)');db.execute('delete from items')
        db.executemany('insert into items values(?,?,?)',[(i['status'], ' '.join(str(i.get(k,'')) for k in ('budget','year','measure','stage','path','source_title','field')),json.dumps(i,ensure_ascii=False)) for i in items])
        db.execute('create index if not exists by_status on items(status)')
    result=dict(structured_zero_facts=sum(f['cents']==0 for f in ref.rows),reviewed=len(items),counts=counts,labels=LABELS,items=items,
      scope='Faits monétaires nuls et détails des registres d’actions/MaPrimeRénov’. Les cases absentes de l’API sont expliquées séparément ; aucun blanc n’est converti en zéro.')
    (out/'zeros-sources.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    with (out/'zeros-sources.csv').open('w',encoding='utf-8-sig',newline='') as file:
        columns=['budget','year','measure','stage','path','category','title','label','reason','raw','line','field','source_title','source_url','source','sha256']
        writer=csv.writer(file,delimiter=';');writer.writerow(columns)
        for item in items:
            values=[str(item.get(k,'')) for k in columns];writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in values])
    return dict(structured_zero_facts=result['structured_zero_facts'],reviewed=len(items),counts=counts,labels=LABELS,scope=result['scope'])
