"""Independent read-only HTTP audit. Python standard library, no AI, no GPU."""
import argparse,collections,csv,datetime,hashlib,html,io,json,os,sqlite3,subprocess,sys,time,traceback,urllib.request,urllib.parse,webbrowser
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from oracle import Reference,STAGES,compare_cells,digest,within
from management import Management
from zeros import source_ledger,classify_cell,LABELS as ZERO_LABELS

HERE=Path(__file__).resolve().parent
def stamp():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def save(p,v):
    t=Path(str(p)+'.tmp');t.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf-8');os.replace(t,p)
def qs(p):return urllib.parse.urlencode({k:dump(v) if isinstance(v,list) else int(v) if isinstance(v,bool) else v for k,v in p.items()})

class Client:
    def __init__(self,base,delay=.05):
        u=urllib.parse.urlsplit(base)
        if u.scheme not in ('http','https') or u.username or u.password or u.query or u.fragment:raise ValueError('URL HTTP(S) simple attendue')
        self.base=base.rstrip('/');self.delay=delay;self.last=0;self.requests=0
    def get(self,route,json_body=True):
        time.sleep(max(0,self.delay-(time.monotonic()-self.last)))
        self.last=time.monotonic();self.requests+=1
        req=urllib.request.Request(self.base+route,headers={'User-Agent':'NosDeniers-AuditIndependant/1.0','Accept':'application/json' if json_body else '*/*'})
        with urllib.request.urlopen(req,timeout=60) as r:
            data=r.read(64*1024*1024+1)
            if len(data)>64*1024*1024:raise ValueError('Réponse trop volumineuse')
            if urllib.parse.urlsplit(r.url).netloc!=urllib.parse.urlsplit(self.base).netloc:raise ValueError('Redirection vers un autre serveur')
        return json.loads(data) if json_body else data

def arithmetic(data,indices):
    errors=[];count=0
    def check(key,wanted,got):
        nonlocal count
        count+=1
        if (wanted is None)!=(got is None) or (got is not None and Decimal(str(got))!=wanted):errors.append(dict(cell=key,expected=None if wanted is None else str(wanted),actual=got))
    for path,series in [(data['parameters']['scope'],data['totals'])]+[(r['id'],r['series']) for r in data['rows']]:
        annuals={a['year']:a for a in series}
        for a in series:
            if set(a.get('comparisons',{}))!={'LFI_PLF','EXEC_LFI','CONSUMPTION'}:errors.append(dict(cell=f'{path} {a["year"]} comparaisons attendues',actual=sorted(a.get('comparisons',{}))))
            if set(a.get('evolution',{}))!=set(STAGES):errors.append(dict(cell=f'{path} {a["year"]} étapes des variations',actual=sorted(a.get('evolution',{}))))
            for stage,rates in a.get('evolution',{}).items():
                if set(rates)!={'nominal_yoy','real_yoy','real_from_start'}:errors.append(dict(cell=f'{path} {a["year"]} {stage} variations attendues',actual=sorted(rates)))
            for name,c in a.get('comparisons',{}).items():
                # Operand identities are specified independently, not accepted from the response.
                operands={'LFI_PLF':['LFI','PLF'],'OUVERT_LFI':['OUVERT','LFI'],'EXEC_LFI':['EXEC','LFI'],
                  'EXEC_OUVERT':['EXEC','OUVERT'],'CONSUMPTION':['EXEC',data['parameters'].get('denominator','LFI')]}.get(name)
                if operands is None:
                    errors.append(dict(cell=f'{path} {a["year"]} comparaison {name}',expected='comparaison connue',actual=name));continue
                if c.get('operands')!=operands:errors.append(dict(cell=f'{path} {name} opérandes',expected=operands,actual=c.get('operands')))
                left,right=(a[s] for s in operands);wanted=None
                if all(x.get('value') is not None and x['status'] in ('ok','excluded') for x in (left,right)):
                    if name!='CONSUMPTION':wanted=Decimal(str(left['value']))-Decimal(str(right['value']))
                    elif right.get('nominal')!=0:wanted=(Decimal(str(left['nominal']))/Decimal(str(right['nominal']))*100).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
                check(f'{path} {a["year"]} {name}',wanted,c.get('value'))
            for stage,rates in a.get('evolution',{}).items():
                for name,c in rates.items():
                    refyear=data['parameters']['start'] if name=='real_from_start' else a['year']-1
                    # A source year is never inferred from the order in the JSON array.
                    if c.get('reference_year')!=refyear:errors.append(dict(cell=f'{path} {stage} {name} année',expected=refyear,actual=c.get('reference_year')))
                    before=annuals.get(refyear);left=a[stage];right=before[stage] if before else None;wanted=None
                    ac=left.get('nominal_cents');bc=right.get('nominal_cents') if right else None
                    valid=ac is not None and bc is not None and bc>0 and all(x.get('nominal_status',x['status']) in ('ok','excluded') for x in (left,right))
                    iy=indices.get(str(a['year']));ib=indices.get(str(refyear));real=name!='nominal_yoy'
                    if valid and (not real or (iy and ib)):
                        rate=Decimal(ac)/Decimal(bc)
                        if real:rate*=Decimal(str(ib))/Decimal(str(iy))
                        wanted=((rate-1)*100).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
                    check(f'{path} {a["year"]} {stage} {name}',wanted,c.get('value'))
    return dict(errors=errors,calculations=count)

def export_check(data,raw):
    errors=[];p=data['parameters'];expected={}
    for path,series in [(p['scope'],data['totals'])]+[(r['id'],r['series']) for r in data['rows']]:
        for a in series:
            for s,label in STAGES.items():expected[(path,a['year'],label)]=a[s]['value']
    seen=set()
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'):
        key=(row['Code'],int(row['Année']),row['Étape']);got=row['Montant EUR']
        if key not in expected or key in seen:errors.append(dict(cell=str(key),expected='case unique connue',actual='inconnue ou doublon'));continue
        seen.add(key);wanted=expected[key]
        if row['Budget']!=p['budget'] or row['Crédits']!=p['measure']:errors.append(dict(cell=str(key),expected=[p['budget'],p['measure']],actual=[row['Budget'],row['Crédits']]))
        if (wanted is None and got!='') or (wanted is not None and (not got or Decimal(got.replace(',','.'))!=Decimal(str(wanted)))):errors.append(dict(cell=str(key),expected=wanted,actual=got))
    if seen!=set(expected):errors.append(dict(cell='lignes exportées',expected=len(expected),actual=len(seen)))
    return dict(errors=errors,export_cells=len(seen))

def params(b,m,scope='',**kw):
    return dict(start=2017,end=2026,budget=b,measure=m,scope=scope,exclude=[],constant=False,base=2025,topic='',topic_mode='only',denominator='LFI')|kw

def plan(ref,quick=False):
    jobs=[]
    for b in ('BG','BA','CAS','CCF'):
        for m in ('AE','CP'):
            scopes=sorted({p for bb,mm,p in ref.children if (bb,mm)==(b,m)}|{''})
            if quick:scopes=[p for p in ('','TA','TA/174','TA/345','TA/345/09') if p in scopes]
            for scope in scopes:
                jobs.append(('tree',params(b,m,scope)))
            for scope in ([''] if quick else [p for p in scopes if p.count('/')<=1]):
                jobs.append(('inflation',params(b,m,scope,constant=True,base=2017)))
            targets=sorted(p for p in ref.paths[(b,m)] if p and p.count('/')<=1)
            if quick:targets=targets[:1]
            for target in targets:jobs.append(('exclusion',params(b,m,target.rpartition('/')[0],exclude=[target])))
            if b=='BG':
                jobs.append(('overlap',params(b,m,'TA',exclude=['TA/174','TA/174/02','TA/174'])))
                for scope in ('','TA','TA/174','TA/345','TA/345/09'):
                    children=sorted(ref.children[(b,m,scope)])
                    if children:jobs.append(('all-excluded',params(b,m,scope,exclude=children[:100])))
                for mode in ('only','without'):
                    for scope in ('','TA','TA/174','VA/135','PR/362'):
                        jobs.append(('topic',params(b,m,scope,topic='maprimerenov',topic_mode=mode)))
                jobs.append(('ecologie-trois-exclusions',params(b,m,'TA',exclude=['TA/345','TA/235'],topic='maprimerenov',topic_mode='without')))
    # Exports on representative roots, and on the two pilot dossiers.
    for b in ('BG','BA','CAS','CCF'):
        for m in ('AE','CP'):jobs.append(('export',params(b,m)))
    for m in ('AE','CP'):
        jobs.append(('export',params('BG',m,'TA',exclude=['TA/345'])))
        jobs.append(('export',params('BG',m,topic='maprimerenov')))
    for b in ('BG','BA','CAS','CCF'):
        for m in ('AE','CP'):
            for constant in (False,True):
                if quick and (b!='BG' or m!='CP' or constant):continue
                jobs.append(('reserves',params(b,m,constant=constant)))
                jobs.append(('movements',params(b,m,'TA/174' if quick else '',constant=constant)))
    return jobs

class Campaign:
    def __init__(self,a):
        self.a=a;self.ref=Reference(a.reference);self.management=Management(self.ref);self.client=Client(a.url,a.delay)
        self.out=a.output.resolve();self.out.mkdir(parents=True,exist_ok=True)
        self.boot=self.client.get('/api/bootstrap');meta=self.boot['meta']
        for k in ('fact_count','data_version','indices'):
            if meta.get(k)!=self.ref.meta.get(k):raise ValueError('Référence différente du site : '+k+'. Actualiser la référence ; aucun certificat émis.')
        self.assets={p:hashlib.sha256(self.client.get(p,False)).hexdigest() for p in ('/','/assets/explorer.js','/assets/explorer.css')}
        self.jobs=plan(self.ref,a.quick)
        self.identity=dict(schema=1,url=a.url,reference=digest(a.reference/'manifest.json'),data_version=meta['data_version'],assets=self.assets,
          code={n:digest(HERE/n) for n in ('audit.py','oracle.py','management.py','zeros.py','document_zeros.py','document-zero-proofs.json')},browser_code=digest(HERE/'browser.cjs'),quick=a.quick,browser=not a.no_browser,planned=len(self.jobs))
        ip=self.out/'identity.json'
        if ip.exists() and json.loads(ip.read_text('utf-8'))!=self.identity:raise ValueError('Site, référence ou outil modifiés : choisir un nouveau dossier de résultats.')
        save(ip,self.identity)
        self.db=sqlite3.connect(self.out/'checkpoints.sqlite')
        self.db.execute('create table if not exists results(id text primary key,kind text,params text,status text,result text,at text)')
        self.db.execute('create table if not exists zero_cases(id text primary key,status text,search text,data text)')
        self.done={i for i,r in self.db.execute('select id,result from results') if not json.loads(r).get('incomplete')};self.changed=False

    def check(self,kind,p):
        if kind=='reserves':
            return self.management.reserves_check(p,self.client.get('/api/reserves?'+qs(p)))
        if kind=='movements':
            items=[];offset=0;visited=set();selection=None;total=None
            while True:
                d=self.client.get('/api/rap-movements?'+qs(p|dict(view='summary',limit=500,offset=offset)))
                if selection is None:selection=d['selection_id'];total=d['count']
                if d['selection_id']!=selection or d['count']!=total:raise ValueError('Mouvements modifiés pendant la pagination')
                items.extend(d['items'])
                if not d['has_more']:break
                nxt=d['next_offset']
                if not isinstance(nxt,int) or nxt<=offset or nxt in visited:raise ValueError('Pagination non progressive')
                visited.add(offset);offset=nxt
            if len(items)!=total:raise ValueError('Pagination incomplète : '+str((len(items),total)))
            return self.management.movement_check(p,items)
        route='/api/explorer?'+qs(p);d=self.client.get(route)
        if d.get('data_version')!=self.ref.meta['data_version']:raise ValueError('Base modifiée pendant le scan')
        if d.get('action_detail_version')!=self.ref.action_hash+':reviewed-disagreements-20260924':raise ValueError('Registre ou règle des actions différent de la référence')
        if d.get('topic_version')!=self.ref.mpr_hash:raise ValueError('Registre MaPrimeRénov différent de la référence')
        result=compare_cells(self.ref,p,d);calc=arithmetic(d,self.ref.indices)
        result['errors']+=calc['errors'];result['calculations']=calc['calculations']
        if kind=='export':
            x=export_check(d,self.client.get('/api/export?'+qs(p),False));result['errors']+=x['errors'];result['export_cells']=x['export_cells']
        result['route']=route
        zero_cells=[]
        for path,series in [(p['scope'],d['totals'])]+[(r['id'],r['series']) for r in d['rows']]:
            for annual in series:
                for stage in STAGES:
                    c=annual[stage];z=classify_cell(self.ref,p,annual['year'],stage,path,c)
                    if z:
                        selected={k:p[k] for k in ('budget','measure','exclude','constant','base','topic','topic_mode')}
                        item=dict(z,budget=p['budget'],measure=p['measure'],year=annual['year'],stage=stage,path=path,selection=selected)
                        identity=dump([selected,annual['year'],stage,path]);ident=hashlib.sha256(identity.encode()).hexdigest()
                        zero_cells.append((ident,z['status'],' '.join(str(item[k]) for k in ('budget','year','measure','stage','path')),dump(item)))
        with self.db:self.db.executemany('insert or replace into zero_cases values(?,?,?,?)',zero_cells)
        return result

    def record(self,ident,kind,p,result):
        status='erreur' if result.get('errors') else 'conforme'
        with self.db:self.db.execute('insert or replace into results values(?,?,?,?,?,?)',(ident,kind,dump(p),status,dump(result),stamp()))
        self.done.add(ident)

    def progress(self):
        counts=dict(self.db.execute('select status,count(*) from results group by status'))
        print(f'{stamp()} — {len(self.done)} contrôles enregistrés / {len(self.jobs)} scénarios API ; {counts.get("erreur",0)} avec anomalie.',flush=True)
        save(self.out/'progress.json',dict(at=stamp(),completed=len(self.done),planned=len(self.jobs),counts=counts))

    def run(self):
        self.progress()
        if 'zero-sources' not in self.done:
            try:
                summary=source_ledger(self.ref,os.environ.get('AUDIT_CORPUS_ROOT','/reference/data'),self.out)
                anomalies=sum(summary['counts'].get(k,0) for k in ('source_blank','source_dash','source_not_applicable','nonzero_source'))
                summary['errors']=[] if not anomalies else [dict(cell='Zéros enregistrés et contenu source',expected='Zéro ou calcul explicite',actual=str(anomalies)+' cas à relire dans le relevé des zéros.')]
                self.record('zero-sources','zero-sources',{},summary)
            except Exception as e:self.record('zero-sources','zero-sources',{},dict(errors=[dict(cell='Relecture des zéros',actual=str(e))],incomplete=True))
        for i,(kind,p) in enumerate(self.jobs):
            ident=kind+':'+hashlib.sha256(dump(p).encode()).hexdigest()[:20]
            if ident in self.done:continue
            try:r=self.check(kind,p)
            except Exception as e:r=dict(errors=[dict(cell='contrôle interrompu',expected='réponse vérifiable',actual=str(e))],incomplete=True)
            self.record(ident,kind,p,r)
            self.progress()
        if not self.a.no_browser and 'browser' not in self.done:
            try:
                config=dict(url=self.a.url,output=str(self.out),scenarios=[p for kind,p in self.jobs if kind in ('export',)][:12])
                save(self.out/'browser-config.json',config)
                env=os.environ.copy();env['NODE_PATH']=os.environ.get('AUDIT_NODE_MODULES',str(self.a.node.parent.parent/'node_modules'))
                r=subprocess.run([str(self.a.node),str(HERE/'browser.cjs'),str(self.out/'browser-config.json')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600,env=env)
                (self.out/'browser.log').write_text(r.stdout+'\n'+r.stderr,'utf-8')
                result=json.loads((self.out/'browser.json').read_text('utf-8'))
                if r.returncode and not result.get('errors'):result['errors']=[dict(cell='navigateur',actual='échec du processus')]
            except Exception as e:result=dict(errors=[dict(cell='navigateur non contrôlé',actual=str(e))],incomplete=True)
            self.record('browser','browser',{},result)
        try:
            after=self.client.get('/api/bootstrap')
            changed=after['meta'].get('data_version')!=self.ref.meta['data_version']
            changed=changed or any(hashlib.sha256(self.client.get(p,False)).hexdigest()!=h for p,h in self.assets.items())
            if changed:raise ValueError('Site modifié pendant la campagne ; relancer un nouveau scan.')
            self.record('stability','stability',{},dict(errors=[]))
        except Exception as e:self.record('stability','stability',{},dict(errors=[dict(cell='version du site',actual=str(e))],incomplete=True))
        return self.report()

    def report(self):
        rows=[dict(id=i,kind=k,params=json.loads(p),status=s,result=json.loads(r),at=t) for i,k,p,s,r,t in self.db.execute('select * from results order by rowid')]
        issues=[dict(case=r['id'],kind=r['kind'],params=r['params'],at=r['at'],**e) for r in rows for e in r['result'].get('errors',[])]
        counts=collections.Counter()
        for r in rows:
            for k in ('amounts','missing','calculations','export_cells','visible_cells'):counts[k]+=r['result'].get(k,0)
        incomplete=any(r['result'].get('incomplete') for r in rows) or self.a.no_browser or len([r for r in rows if r['kind'] not in ('browser','stability','zero-sources')])!=len(self.jobs) or not any(r['kind']=='stability' for r in rows)
        verdict='INCOMPLET' if incomplete else 'ANOMALIES DÉTECTÉES' if issues else 'CONFORME SUR LE PÉRIMÈTRE CONTRÔLÉ'
        report=dict(at=stamp(),verdict=verdict,passed=not issues and not incomplete,identity=self.identity,counts=dict(counts),
          zero_source_summary=next((r['result'] for r in rows if r['kind']=='zero-sources'),{}),zero_case_counts=dict(self.db.execute('select status,count(*) from zero_cases group by status')),
          cases=len(rows),error_count=len(issues),issues=issues,documented_disagreements=len(self.ref.warnings),
          limits=['Comparaison indépendante à la base structurée et aux registres figés ; les documents officiels ne sont pas tous réextraits.',
           'Les cases manquantes restent des données manquantes ; leur absence dans les publications n’est pas démontrée.',
           'Tableau des crédits, niveaux de détail, montants des réserves et lignes de mouvements : comparaison à la référence. Les réconciliations documentaires ne sont pas refaites intégralement.',
           'Les parcours navigateur sont un échantillon explicite ; aucune promesse sur toutes les combinaisons possibles.'],
          excluded_sections=['Actes juridiques de la chronologie et pièces justificatives détaillées des mouvements : non certifiés indépendamment.','Recherche documentaire : pertinence des réponses non évaluée.'],
          checkpoint_resume=True,site_modified=False,ai_calls=0)
        save(self.out/'rapport.json',report)
        with (self.out/'anomalies.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';');w.writerow(['Contrôle','Case','Attendu','Observé','Lien'])
            for e in issues:
                safe=lambda v: "'"+str(v) if str(v).startswith(('=','+','-','@')) else str(v)
                w.writerow([safe(e['kind']),safe(e.get('cell','')),safe(e.get('expected','')),safe(e.get('actual','')),self.a.url+'/?'+qs(e['params'])])
        esc=lambda v:html.escape(str(v))
        cards=''.join(f'<div><strong>{v:,}</strong><span>{label}</span></div>'.replace(',',' ') for v,label in [(counts['amounts'],'montants comparés'),(counts['calculations'],'calculs vérifiés'),(counts['missing'],'cases sans montant contrôlées'),(len(issues),'anomalies')])
        cases=''.join(f'<tr><td>{esc(e["kind"])}</td><td>{esc(e.get("cell",""))}</td><td>{esc(e.get("expected",""))}</td><td>{esc(e.get("actual",""))}</td><td><a href="{esc(self.a.url+"/?"+qs(e["params"]))}">Voir</a></td></tr>' for e in issues[:500])
        page=f'''<!doctype html><html lang="fr"><meta charset="utf-8"><title>Audit indépendant — Nos Deniers</title>
<style>body{{font:16px/1.55 system-ui;margin:40px auto;max-width:1250px;padding:0 24px;background:#f5f8fc;color:#16364d}}h1{{font-size:30px;margin-bottom:4px}}.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}}.cards div{{background:white;border:1px solid #d5e0eb;border-radius:12px;padding:16px;flex:1;min-width:170px}}strong,span{{display:block}}strong{{font-size:27px}}.verdict{{padding:16px;border-left:5px solid {'#a33' if issues or incomplete else '#267b54'};background:white;font-weight:700}}table{{border-collapse:collapse;width:100%;background:white;font-size:13px}}td,th{{padding:10px;border:1px solid #dbe3eb;text-align:left;overflow-wrap:anywhere}}details{{background:white;padding:15px;margin:15px 0}}a{{color:#175897}}</style>
<h1>Nos Deniers · Audit indépendant</h1><p>{esc(report['at'])} · <a href="{esc(self.a.url)}">{esc(self.a.url)}</a></p>
<div class="verdict">{esc(verdict)}</div><div class="cards">{cards}</div>
<p>Les nombres ci-dessus comptent des vérifications, pas des montants uniques : une même donnée peut être testée sous plusieurs filtres. AE et CP sont distingués. Aucun calcul d’IA.</p>
<h2>Ce que prouve ce contrôle</h2><p>Les montants sont recherchés dans une référence séparée par budget, année, mission, programme, action, sous-action, étape et type de crédit. Les calculs de l’application ne sont pas réutilisés. Un montant attendu et sa position sont comparés au résultat de l’API.</p>
<p>Les montants sont comparés au centime : aucun seuil de tolérance ne masque une erreur de restitution. Les écarts entre documents déjà signalés ({len(self.ref.warnings)} groupes dans la référence) restent distincts.</p>
<h2>Couverture et limites</h2><ul>{''.join('<li>'+esc(t)+'</li>' for t in report['limits']+report['excluded_sections'])}</ul>
<p>Base de référence : {self.ref.meta['fact_count']:,} faits. Version : <code>{esc(self.ref.meta['data_version'])}</code>. Référence et scripts sont identifiés par empreinte ; les résultats sont sauvegardés après chaque scénario.</p>
<h2>Zéros et cases sans montant</h2><p>Une relecture dédiée distingue les zéros effectivement présents dans les cellules sources, les calculs nuls, les mentions documentaires et les sens non déterminés. Un blanc ou un tiret ne suffit jamais à prouver un zéro.</p><p><a href="zeros-sources.csv">Relevé des zéros sources · CSV</a> · <a href="zeros-sources.json">Détail des preuves · JSON</a></p><ul>{"".join("<li>"+esc(ZERO_LABELS.get(k,k))+" : "+str(v)+"</li>" for k,v in report["zero_source_summary"].get("counts",{}).items())}</ul><p>Ce relevé reste distinct de la conformité des montants restitués par le site. Une source non relue ne devient pas une preuve de zéro.</p><h2>Anomalies</h2><p>{len(issues)} anomalie(s). <a href="anomalies.csv">Télécharger le détail CSV</a> · <a href="rapport.json">Rapport technique</a></p>
<table><thead><tr><th>Contrôle</th><th>Case</th><th>Attendu</th><th>Observé</th><th>Site</th></tr></thead><tbody>{cases or '<tr><td colspan="5">Aucune anomalie dans les contrôles terminés.</td></tr>'}</tbody></table>
<details><summary>Scénarios enregistrés : {len(rows)}</summary><ul>{''.join('<li>'+esc(r['kind']+' — '+r['status']+' — '+dump(r['params']))+'</li>' for r in rows)}</ul></details>
<p>Ce rapport ne signifie jamais que toutes les données publiques possibles ont été collectées. Le site et la base sont restés inchangés.</p></html>'''
        (self.out/'rapport.html').write_text(page,'utf-8');print(dump(dict(verdict=verdict,counts=dict(counts),errors=len(issues),report=str(self.out/'rapport.html'))),flush=True)
        return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='https://budget.lexmachine.net')
    p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--quick',action='store_true')
    p.add_argument('--resume-last',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--open',action='store_true');p.add_argument('--delay',type=float,default=.05)
    p.add_argument('--node',type=Path,default=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    a=p.parse_args()
    if a.resume_last:
        saved=json.loads((HERE/'dernier-scan.json').read_text('utf-8'))
        for k,v in saved.items():setattr(a,k,Path(v) if k in ('reference','output') else v)
    if a.reference is None:a.reference=Path(json.loads((HERE/'reference-selection.json').read_text('utf-8'))['path'])
    if a.output is None:a.output=HERE/'resultats'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    a.output.mkdir(parents=True,exist_ok=True)
    save(HERE/'dernier-scan.json',dict(output=str(a.output.resolve()),reference=str(a.reference.resolve()),url=a.url,quick=a.quick,no_browser=a.no_browser))
    try:
        campaign=Campaign(a);result=campaign.run();rc=0 if result['passed'] else 2
    except KeyboardInterrupt:
        print('Interrompu. Résultats enregistrés : relancer REPRENDRE_LE_SCAN.cmd.',flush=True)
        if 'campaign' in locals():campaign.report()
        rc=130
    except Exception as e:
        save(a.output/'ECHEC.json',dict(at=stamp(),error=str(e),traceback=traceback.format_exc(),passed=False))
        (a.output/'rapport.html').write_text('<meta charset="utf-8"><h1>Audit incomplet</h1><p>'+html.escape(str(e))+'</p><p>Aucun certificat de conformité émis. Le site est inchangé.</p>','utf-8')
        print('Audit incomplet : '+str(e));rc=2
    if a.open:webbrowser.open((a.output/'rapport.html').resolve().as_uri())
    return rc
if __name__=='__main__':sys.exit(main())
