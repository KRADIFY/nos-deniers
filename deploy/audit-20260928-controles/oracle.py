"""Reference arithmetic. Standard library only; never imports the website.

The reference is the published structured database plus its documentary registries.
This proves restitution of those inputs, not their universal documentary accuracy.
"""
import collections
import hashlib
import json
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

STAGES = {'PLF':'Proposé en PLF','LFI':'Voté en LFI','EXEC':'Consommé',
 'OUVERT':'Crédits ouverts','REPORT_ENTRANT':'Reports de N−1','LEGIS':'Ajustements nets de crédits',
 'REGLEMENT':'Mouvements réglementaires nets','FDC':'FdC et AdP rattachés','FDC_PREVU':'FdC et AdP prévus',
 'FONGIBILITE':'Fongibilité des crédits','PLRG_OUVERTURE':'Ouvertures proposées en PLRG',
 'PLRG_ANNULATION':'Annulations proposées en PLRG','REPORT_SORTANT':'Reports vers N+1'}
ACTION_FILES = ['actions-p174.json','actions-ecologie.json','actions-multititres.json',
 'actions-sousactions.json','actions-national.json','actions-dette.json','actions-rap-historique.json']
REVIEWED = {(2023,'AB','354','AE'),(2023,'AB','354','CP'),(2023,'EC','140','AE'),
 (2023,'EC','141','AE'),(2023,'GA','156','AE'),(2023,'GA','302','AE'),(2023,'JA','166','AE'),
 (2023,'PR','364','AE'),(2023,'RA','150','AE'),(2023,'SB','176','AE'),(2023,'SE','124','AE'),
 (2023,'SF','219','AE'),(2023,'TR','368','AE'),(2024,'JA','166','AE'),
 (2024,'SB','176','AE'),(2025,'TB','155','AE')}

def digest(p):
    with Path(p).open('rb') as f:
        h=hashlib.sha256()
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
        return h.hexdigest()

def read(p): return json.loads(Path(p).read_text('utf-8'))
def within(path,parent): return not parent or path==parent or path.startswith(parent+'/')
def money(item): return item['cents'] if 'cents' in item else item['euros']*100
def nodepath(r): return '/'.join(str(r[k]) for k in ('mission','program','action','subaction') if r.get(k))
def rounding_ok(a,b,terms=1):
    return abs(a-b)<=min(1000,max(100,50*(terms+1),abs(b)//1000))

class Reference:
    def __init__(self, folder):
        self.folder=Path(folder); self.manifest=read(self.folder/'manifest.json')
        for name,expected in self.manifest['files'].items():
            p=(self.folder/name).resolve()
            if not p.is_relative_to(self.folder.resolve()) or digest(p)!=expected:
                raise ValueError('Référence modifiée ou endommagée : '+name)
        db=sqlite3.connect((self.folder/'budget.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite non intègre')
        self.meta={r['key']:json.loads(r['value']) for r in db.execute('select * from meta')}
        self.sources={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')}
        self.rows=[dict(r) for r in db.execute('select * from facts')];db.close()
        if len(self.rows)!=self.meta['fact_count']:raise ValueError('Décompte de référence incohérent')
        self.indices=self.meta['indices'];self.amounts=collections.defaultdict(int)
        self.source_ids=collections.defaultdict(set);self.paths=collections.defaultdict(set)
        self.blocked=set();self.labels={};self.group_rows=collections.defaultdict(list)
        self.warnings=[];self.leaves=set();self.roots_by_bucket=collections.defaultdict(set)
        for r in self.rows:
            if type(r['cents']) is not int or r['measure'] not in ('AE','CP') or r['stage'] not in STAGES:
                raise ValueError('Fait de référence invalide : '+str(r))
            if r['source'] not in self.sources:raise ValueError('Source de référence absente : '+r['source'])
            if r['year']==2026 and r['mission']=='M26985a5788':
                r['mission']='MB';r['mission_label']='Monde combattant, mémoire et liens avec la Nation'
            b,m,y,s=r['budget'],r['measure'],r['year'],r['stage'];path=nodepath(r)
            self.group_rows[(b,m,y,s,r['mission']+'/'+r['program'])].append(r)
            self.roots_by_bucket[(b,m,y,s)].add(r['mission']+'/'+r['program'])
            bits=path.split('/');self.leaves.add((b,m,y,s,path))
            for i in range(len(bits)+1):
                p='/'.join(bits[:i]);key=(b,m,y,s,p)
                self.amounts[key]+=r['cents'];self.source_ids[key].add(r['source'])
                self.paths[(b,m)].add(p)
                if i:
                    label=r[('mission_label','program_label','action_label','subaction_label')[i-1]]
                    if y>=self.labels.get((b,m,p),(-1,''))[0]:self.labels[(b,m,p)]=(y,label)
        self.documentary_nodes=set();self.groups=[];raw=[]
        for name in ACTION_FILES:
            p=self.folder/'registries'/name
            if p.exists():raw.append(p.read_bytes());self.groups.extend(read(p)['groups'])
        self.action_hash=hashlib.sha256(b'\0'.join(raw)).hexdigest()
        group_keys=set()
        for g in self.groups:
            key=(g['budget'],g['measure'],g['year'],g['stage'],g['mission']+'/'+g['program'])
            if key in group_keys:raise ValueError('Groupe documentaire en double : '+str(key))
            group_keys.add(key);self.documentary_nodes.add(key)
            parents=g.get('parents') or [g['parent']];actual=list(self.group_rows.get(key,[]))
            for p in parents:
                match=next((r for r in actual if all(r.get(k)==v for k,v in p.items())),None)
                if match is None:raise ValueError('Parent documentaire périmé : '+str(key))
                actual.remove(match)
            if actual or self.sources[g['source']]['sha256']!=g['sha256']:
                raise ValueError('Registre documentaire et base différents : '+str(key))
            parent=sum(p['cents'] for p in parents)
            published=g.get('published_total_cents',g.get('published_total_euros',0)*100)
            actions=sum(money(a) for a in g['actions'])
            special=(g['year'],g['mission'],g['program'],g['measure']) in REVIEWED and g['stage']=='EXEC' and g['budget']=='BG'
            special=special and bool(g.get('reconciliation_note')) and abs(actions-published)<=100 and abs(published-parent)*10000<=abs(parent)*150
            blocked=bool(g.get('review_required')) or not rounding_ok(actions,parent,len(g['actions'])) or not rounding_ok(published,parent)
            if g.get('action_reconstruction'):blocked=bool(g.get('review_required')) or not rounding_ok(actions,parent,len(g['actions']))
            blocked=blocked and not special
            if actions!=parent:self.warnings.append(dict(key=key,difference_cents=actions-parent,documented=bool(g.get('reconciliation_note')),blocked=blocked))
            if blocked:self.blocked.add(key)
            for a in g['actions']:
                child=key[:-1]+(key[-1]+'/'+a['code'],)
                self.install(child,money(a),g['source'],a['label'],available=not blocked)
                subs=a.get('subactions',[])
                subblocked=blocked or a.get('subactions_review',{}).get('status')=='review_required' or (subs and not rounding_ok(sum(money(t) for t in subs),money(a),len(subs)))
                if subblocked:self.blocked.add(child)
                for t in subs:self.install(child[:-1]+(child[-1]+'/'+t['code'],),money(t),g['source'],t['label'],available=not subblocked)
        self.mpr=read(self.folder/'registries/maprimerenov.json')
        self.mpr_hash=digest(self.folder/'registries/maprimerenov.json')
        self.sources.update({s['id']:s for s in self.mpr['sources']})
        self.children=collections.defaultdict(set)
        for b,m in self.paths:
            for path in self.paths[(b,m)]:
                if path:self.children[(b,m,path.rpartition('/')[0])].add(path)
        self.years=sorted({r['year'] for r in self.rows})
        self.children_by_year=collections.defaultdict(set)
        for b,m,y,stage,path in set(self.amounts)|self.documentary_nodes:
            if path:self.children_by_year[(b,m,y,path.rpartition('/')[0])].add(path)

    def children_in_period(self,p):
        result=set()
        for year in range(p['start'],p['end']+1):
            result.update(self.children_by_year.get((p['budget'],p['measure'],year,p['scope']),set()))
        return result

    def install(self,key,amount,source,label,available):
        b,m,y,_,p=key;self.paths[(b,m)].add(p);self.documentary_nodes.add(key)
        if y>=self.labels.get((b,m,p),(-1,''))[0]:self.labels[(b,m,p)]=(y,label)
        if available:self.amounts[key]=amount;self.source_ids[key]={source}

    def converted(self,amount,year,params):
        if amount is None:return None
        if not params.get('constant'):return Decimal(amount)/100
        iy=self.indices.get(str(year));ib=self.indices.get(str(params.get('base',2025)))
        if not iy or not ib:return None
        return (Decimal(amount)*Decimal(str(ib))/Decimal(str(iy))).quantize(Decimal(1),rounding=ROUND_HALF_UP)/100

    def removed(self,key,excluded):
        """Set-union subtraction, with complete branches collapsed to their parent."""
        path=key[-1]
        if any(within(path,e) for e in excluded):return self.amounts.get(key),True
        finer={e for e in excluded if within(e,path)}
        if not finer:return 0,False
        if key in self.blocked:return None,False
        children=[key[:-1]+(p,) for p in self.children[(key[0],key[1],path)] if key[:-1]+(p,) in self.amounts]
        if not children:return None,False
        if (key in self.leaves or key in getattr(self,'documentary_nodes',set())) and any(not any(within(e,c[-1]) for c in children) for e in finer):return None,False
        parts=[self.removed(c,finer) for c in children]
        if any(v is None for v,_ in parts):return None,False
        if all(full for _,full in parts):return self.amounts[key],True
        return sum(v for v,_ in parts),False

    def expected(self,params,year,stage,path):
        key=(params['budget'],params['measure'],year,stage,path);excluded=params.get('exclude',[])
        amount=self.amounts.get(key)
        if amount is not None:
            # Canonical parent totals must never be recomputed from a differing breakdown.
            roots=[] if not excluded else [key[:4]+(p,) for p in self.roots_by_bucket[key[:4]] if within(p,path)]
            if excluded and len(path.split('/'))<=2 and roots:
                parts=[]
                for root in set(r[:-1]+('/'.join(r[-1].split('/')[:2]),) for r in roots):
                    x,full=self.removed(root,excluded)
                    if x is None:return None
                    parts.append(x)
                amount-=sum(parts)
            elif excluded:
                x,full=self.removed(key,excluded)
                if x is None:return None
                amount-=x
        if params.get('topic'):
            part=self.topic_amount(params,year,stage,path)
            if params.get('topic_mode','only')=='only':return part
            if year<2020 or params['budget']!='BG':return amount
            carriers=[c['path'] for c in self.mpr['carriers'] if (within(c['path'],path) or within(path,c['path'])) and not any(within(c['path'],e) or within(path,e) for e in excluded)]
            if not carriers:return amount
            if part is None or amount is None:return None
            amount-=part
            if amount<0:return None
        return amount

    def topic_amount(self,p,year,stage,path):
        if year<2020 or p['budget']!='BG':return None
        excluded=p.get('exclude',[])
        facts=[r for r in self.mpr['facts'] if (r['year'],r['stage'],r['measure'])==(year,stage,p['measure'])]
        targets=set()
        for c in self.mpr['carriers']:
            known=[nodepath(r) for r in facts if within(nodepath(r),c['path'])]
            targets.update(known or [c['path']])
        targets={t for t in targets if (within(t,path) or within(path,t)) and not any(within(t,e) or within(path,e) for e in excluded)}
        if not targets:return 0
        evidence=[e for e in self.mpr.get('perimeter_evidence',[]) if e['year']==year and stage in e['stages'] and p['measure'] in e['measures'] and (within(e['path'],path) or within(path,e['path'])) and not any(within(e['path'],x) or within(path,x) for x in excluded)]
        active=[t for t in targets if not any(within(t,e['path']) for e in evidence)]
        covered={t for c in self.mpr['coverage'] if (c['year'],c['stage'],c['measure'])==(year,stage,p['measure']) for t in c['paths']}
        if any((path!=t and within(path,t)) or any(e!=t and within(e,t) for e in excluded) or not any(within(t,c) for c in covered) for t in active):return None
        selected=[r for r in facts if within(nodepath(r),path) and not any(within(nodepath(r),e) for e in excluded)]
        if any(not any(within(nodepath(r),t) or within(t,nodepath(r)) for r in selected) for t in active):return None
        return sum(r['cents'] for r in selected)

def compare_cells(ref,params,data):
    errors=[];checked=missing=0
    def issue(where,expected,actual):errors.append(dict(cell=where,expected=expected,actual=actual))
    years=list(range(params['start'],params['end']+1))
    if data.get('years')!=years:issue('années',years,data.get('years'))
    if data.get('stages')!=STAGES:issue('colonnes des étapes',STAGES,data.get('stages'))
    for k in ('budget','measure','scope','start','end','topic','topic_mode','constant','base','exclude'):
        wanted=params.get(k,{'topic':'','topic_mode':'only','constant':False,'base':2025,'exclude':[]}.get(k))
        if data.get('parameters',{}).get(k)!=wanted:issue('paramètre '+k,wanted,data.get('parameters',{}).get(k))
    rows=data.get('rows',[]);ids=[r['id'] for r in rows]
    if len(ids)!=len(set(ids)):issue('lignes en double','identifiants uniques',ids)
    if not params.get('topic'):
        wanted=ref.children_in_period(params)
        if set(ids)!=wanted:issue('lignes / bonnes cases',sorted(wanted),sorted(ids))
    for path,series in [(params['scope'],data.get('totals',[]))]+[(r['id'],r['series']) for r in rows]:
        if [a['year'] for a in series]!=years:issue(path+' années des lignes',years,[a['year'] for a in series])
        for annual in series:
            year=annual['year']
            for stage in STAGES:
                cell=annual.get(stage,{})
                key=f"{params['budget']} | {params['measure']} | {path or 'TOTAL'} | {year} | {stage}"
                wanted=ref.expected(params,year,stage,path);actual=cell.get('nominal_cents')
                if actual is None and cell.get('status')=='excluded' and cell.get('nominal')==0:actual=0
                if wanted!=actual:issue(key+' montant en centimes',wanted,actual)
                nominal=cell.get('nominal');value=cell.get('value');converted=ref.converted(wanted,year,params)
                if (nominal is None)!=(wanted is None) or (nominal is not None and Decimal(str(nominal))!=Decimal(wanted)/100):issue(key+' euros courants',None if wanted is None else str(Decimal(wanted)/100),nominal)
                if (value is None)!=(converted is None) or (value is not None and Decimal(str(value))!=converted):issue(key+' euros affichés',None if converted is None else str(converted),value)
                if wanted is None:
                    missing+=1
                    if not cell.get('reason') or cell.get('status') in ('ok','excluded'):issue(key+' absence expliquée','motif explicite',cell.get('status'))
                else:
                    checked+=1
                    if cell.get('status')!='excluded' and not cell.get('sources'):issue(key+' sources','références présentes',cell.get('sources'))
                    if not params.get('exclude') and not params.get('topic') and hasattr(ref,'source_ids'):
                        required=ref.source_ids[(params['budget'],params['measure'],year,stage,path)]
                        absent=required-set(cell.get('sources',[]))
                        if absent:issue(key+' origine de la case',sorted(required),cell.get('sources',[]))
                    unknown=set(cell.get('sources',[]))-set(ref.sources)
                    if unknown:issue(key+' source inconnue',[],sorted(unknown))
    return dict(errors=errors,amounts=checked,missing=missing)
