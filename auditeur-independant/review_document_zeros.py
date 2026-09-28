"""Reproducible case review, separate from the website's extraction code."""
import json,re,collections
from pathlib import Path
from oracle import digest

ROOT=Path('references/physical-sources'); OUT=Path('resultats/document-zero-pages')
FIELDS=('source','year','budget','mission','program','action','subaction','stage','measure','category','title','line','field')
def signature(f):return {k:f.get(k,'') for k in FIELDS}
def lines(words):
    groups=[]
    for w in sorted(words,key=lambda w:((w['yMin']+w['yMax'])/2,w['xMin'])):
        cy=(w['yMin']+w['yMax'])/2
        if not groups or abs(cy-groups[-1][0])>2:groups.append((cy,[w]))
        else:groups[-1][1].append(w)
    return [sorted(ws,key=lambda w:w['xMin']) for _,ws in groups]
def text(ws):return ' '.join(w['text'] for w in ws)
def box(ws):return [min(w['xMin'] for w in ws)-.1,min(w['yMin'] for w in ws)-.1,max(w['xMax'] for w in ws)+.1,max(w['yMax'] for w in ws)+.1]
def fragment(ws,role):return dict(box=box(ws),text=text(ws),role=role)
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'))
tables=json.loads(Path('resultats/html-zero-tables.json').read_text('utf-8'))
proofs=[];pending=[]
for g in groups:
    s=g['source'];assert digest(ROOT/s['path'])==s['sha256']
    for f in g['rows']:
        p=dict(fact=signature(f),sha256=s['sha256'],source_url=s['url'],source_title=s['title'],reviewed_on='2026-09-28')
        if s['format']=='html':
            n=int(re.search(r'tableau (\d+)',f['field'])[1]);row=f['line'];col=1 if f['measure']=='AE' else 2
            cells=tables[n-1][row-1];header=tables[n-1][0]
            if cells[0]!=f['program_label'] or cells[col]!='0':pending.append((f,'html label/value mismatch'));continue
            p.update(kind='html',table=n,row=row,column=col+1,header=header,cells=cells,raw='0',status='source_zero',reason='Zéro écrit dans la LFI, au croisement du programme et de la colonne AE/CP. L’intitulé, l’en-tête et la cellule ont été relus.')
            proofs.append(p);continue
        name=f"{s['id']}-{f['line']}"
        ws=json.loads((OUT/(name+'.json')).read_text('utf-8'));ls=lines(ws)
        # Summary rows are explicitly labelled with both the budget stage and AE/CP.
        ending={'LFI':('prévues en LFI' if f['measure']=='AE' else 'prévus en LFI'),
                'EXEC':('consommées' if f['measure']=='AE' else 'consommés'),
                'OUVERT':('ouvertes' if f['measure']=='AE' else 'ouverts')}[f['stage']]
        prefix='Total des '+f['measure']+' '+ending
        candidates=[l for l in ls if text(l).startswith(prefix+' ')]
        # The first recap belongs to this exercise; later recap is explicitly N-1.
        current=[l for l in ls if text(l).startswith(str(f['year'])+' /')]
        if candidates and current:
            l=candidates[0];label=l[:len(prefix.split())];nums=l[len(prefix.split()):]
            if nums and all(w['text']=='0' for w in nums):
                p.update(kind='pdf',page=f['line'],fragments=[fragment(current[0],'exercise'),fragment(label,'row'),fragment(nums,'value')],raw=text(nums),status='source_zero',reason='Zéro imprimé sur la ligne de total du RAP pour cet exercice, cette étape et ce type de crédits. Les cellules vides voisines ne sont pas utilisées.')
                proofs.append(p);continue
        pending.append((f,[(i,text(l)) for i,l in enumerate(ls) if any(t in text(l) for t in ('Total des','E1','P1','LFI 2018','Programme 869'))]))
Path('document-zero-proofs.json').write_text(json.dumps(dict(version=1,proofs=proofs),ensure_ascii=False,indent=2),'utf-8')
Path('resultats/document-zero-pending.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2),'utf-8')
print('Confirmed',len(proofs),'Pending',len(pending),'by kind',collections.Counter(p['kind'] for p in proofs))
for f,why in pending:print(f['source'],f['line'],f['program'],f['year'],f['stage'],f['measure'],str(why)[:220])
