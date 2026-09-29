"""Local Selenium navigation audit. No AI, no change to budget data or production."""
import argparse,datetime,hashlib,html,json,os,subprocess,sys,time,traceback,urllib.request,zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.runtime/selenium-libs'))
os.environ.setdefault('SE_CACHE_PATH',str(ROOT/'.runtime/selenium-cache'))
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait,Select
from selenium.common.exceptions import StaleElementReferenceException
from expanded_navigation import ExpandedControls
NAV=['credits','ecologie','maprimerenov','movements','documents','coverage']
class Check(ExpandedControls):
 def __init__(self,a):
  self.a=a;self.server=None;self.driver=None;self.rows=[];self.seen={};self.clicked=set();self.started=time.monotonic();self.checked_cells=0;self.transitions=0;self.latencies=[];self.links={};self.finished=False;self.documents_summary=None;self.proofs_checked=0;self.active_scope=None;self.last_action=None;self.source_signature={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('public/assets/explorer.js','public/assets/explorer.css','public/explorer.html','budget_service/api.py')}
  resume=getattr(a,'resume',None)
  self.out=Path(resume).resolve() if resume else ROOT/'reports/navigation-selenium'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
  if resume:
   if not self.out.is_relative_to((ROOT/'reports/navigation-selenium').resolve()):raise ValueError('Dossier de reprise hors des rapports de navigation')
   old=json.loads((self.out/'result.json').read_text(encoding='utf-8'))
   if old.get('source_files')!=self.source_signature or old.get('url')!=a.url:raise ValueError('Version ou URL différente : créer une nouvelle campagne')
   if old.get('execution_finished'):raise ValueError('Cette campagne est déjà terminée')
   (self.out/('avant-reprise-'+str(time.time_ns())+'.json')).write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
   self.rows=old['results'];self.seen=old.get('inventory',{});self.clicked=set(self.seen)-set(old.get('unexercised_families',[]));self.links=old.get('links',{})
   self.checked_cells=old.get('rendered_cells_checked',0);self.transitions=old.get('settled_transitions',0);self.latencies=old.get('latencies_seconds',[]);self.proofs_checked=old.get('proofs_checked',0);self.started-=old.get('elapsed_seconds',0)
  else:self.out.mkdir(parents=True)
  self.downloads=self.out/'downloads';self.downloads.mkdir(exist_ok=True)
 def save(self):
  missing=sorted(set(self.seen)-self.clicked)
  result=dict(at=datetime.datetime.now().astimezone().isoformat(),url=self.a.url,elapsed_seconds=round(time.monotonic()-self.started),results=self.rows,failed=sum(r['status']=='echec' for r in self.rows),skipped=sum(r['status']=='non_execute' for r in self.rows),control_families_seen=len(self.seen),control_families_exercised=len(self.clicked),unexercised_families=missing,inventory=self.seen,execution_finished=self.finished,proofs_checked=self.proofs_checked,active_scope=self.active_scope,all_combinations_covered=False,links_seen=len(self.links),documents=self.documents_summary,scope='Navigation et disponibilité documentaire. Ne certifie pas les montants. Le mode complet parcourt les postes 2017–2026 et leurs commandes ; les croisements de filtres sont testés par paires. Toutes les suites de clics et toutes les combinaisons d’exclusions ne sont pas couvertes.',rendered_cells_checked=self.checked_cells,settled_transitions=self.transitions,latencies_seconds=self.latencies,source_js_sha256=self.source_signature['public/assets/explorer.js'],source_files=self.source_signature)
  result['links']=self.links
  result['passed']=not result['failed'];result['complete']=self.finished and result['passed'] and not result['skipped'] and not missing
  temp=self.out/'result.tmp';temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.out/'result.json')
  rows=''.join('<tr><td>'+html.escape(r['name'])+'</td><td>'+html.escape(r['status'])+'</td><td>'+html.escape(r.get('detail',''))+'</td></tr>' for r in self.rows)
  page='<!doctype html><meta charset="utf-8"><title>Nos Deniers — Navigation</title><style>body{font:16px system-ui;color:#163c55;max-width:1100px;margin:40px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}h1{font-size:28px}</style><h1>Contrôle de navigation Nos Deniers</h1><p>'+str(len(self.rows))+' scénarios enregistrés · '+str(result['failed'])+' échecs · '+str(result['skipped'])+' non exécutés.</p><p>'+html.escape(result['scope'])+'</p><table><tr><th>Parcours</th><th>Résultat</th><th>Détail</th></tr>'+rows+'</table><h2>Commandes rencontrées sans activation</h2><p>'+html.escape(', '.join(self.seen[k].get('label') or k for k in missing) or 'Aucune dans l’inventaire rencontré.')+'</p><p>Les captures des échecs, téléchargements et détails sont conservés dans ce dossier. Un échec réseau n’est pas assimilé à une erreur de montant.</p>'
  page+='<h2>Documents et liens</h2><p><a href="documents/rapport-liens.html">Contrôle des documents</a></p>' if self.documents_summary else ''
  page+='<p>'+('Campagne terminée.' if self.finished else 'Campagne en cours ou interrompue. Aucun bilan final.')+'</p>'
  (self.out/'rapport.html').write_text(page,encoding='utf-8');return result
 def inventory(self):
  rows=self.driver.execute_script("""return [...document.querySelectorAll('button,select,input,summary')].filter(e=>e.getClientRects().length).map(e=>({key:e.id?'#'+e.id:e.tagName==='SUMMARY'?'summary':Object.keys(e.dataset).length?'['+Object.keys(e.dataset).sort().join(',')+']':e.tagName.toLowerCase()+'.'+e.className,label:(e.innerText||e.getAttribute('aria-label')||e.name||'').slice(0,100),disabled:e.disabled||false}));""")
  for row in rows:self.seen[row['key']]=row
  links=self.driver.execute_script("return [...document.querySelectorAll('a[href]')].filter(e=>e.getClientRects().length).map(e=>({url:e.href,raw:e.getAttribute('href'),label:e.textContent.trim()}));")
  for link in links:self.links[link['url']]=link
 def mark(self,e):
  key=self.driver.execute_script("return arguments[0].id?'#'+arguments[0].id:arguments[0].tagName==='SUMMARY'?'summary':Object.keys(arguments[0].dataset).length?'['+Object.keys(arguments[0].dataset).sort().join(',')+']':arguments[0].tagName.toLowerCase()+'.'+arguments[0].className",e);self.clicked.add(key)
 def wait(self):
  def done(d):
   error=d.find_element(By.ID,'error')
   if error.is_displayed():raise RuntimeError(error.text)
   return d.execute_script("return document.getElementById('loading').hidden && (!window.__navCheck || __navCheck.pending===0)")
  start=time.monotonic();WebDriverWait(self.driver,100).until(done);self.inventory();self.transitions+=1;self.latencies.append(round(time.monotonic()-start,3));self.check_cells()
 def check_cells(self):
  result=self.driver.execute_script(r"""if(!data || view!=='credits' || !['compare','series'].includes(mode))return {count:0,errors:[]};
   const errors=[];let count=0;
   for(const key of ['start','end','budget','measure','scope','topic','topic_mode','constant','base'])if(String(state[key])!==String(data.parameters[key]))errors.push('Sélection non appliquée: '+key);
   const unit=Number(document.getElementById('unit').value),digits=unit===1?0:1;
   const format=new Intl.NumberFormat('fr-FR',{minimumFractionDigits:digits,maximumFractionDigits:digits});
   const tidy=s=>String(s).replace(/\s/g,'');
   for(const b of document.querySelectorAll('#credits-table [data-year][data-stage][data-cell-scope]')){
    const scope=b.dataset.cellScope,annual=(scope===state.scope?data.totals:data.rows.find(r=>r.id===scope)?.series)?.find(y=>y.year===Number(b.dataset.year)),cell=annual?.[b.dataset.stage];count++;
    if(!cell){errors.push('Cellule sans référence '+scope+'/'+b.dataset.year+'/'+b.dataset.stage);continue;}
    const text=[...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('');
    if(cell.value===null || cell.value===undefined){if(!/disponible|applicable/i.test(b.textContent))errors.push('Absence sans explication '+scope);}
    else {const expected=(cell.approximate?'≈':'')+tidy(format.format(cell.value/unit))+(cell.status==='partial'?'*':'');if(tidy(text)!==expected)errors.push('Restitution différente '+scope+'/'+b.dataset.year+'/'+b.dataset.stage+': '+text+' / '+expected);}
   }
   if(!count)errors.push('Tableau sans cellule');return {count,errors};""")
  self.checked_cells+=result['count'];assert not result['errors'],'; '.join(result['errors'][:5])
 def click(self,selector):
  self.last_action={'selector':selector,'page':self.driver.current_url}
  e=WebDriverWait(self.driver,30).until(lambda d:next((x for x in d.find_elements(By.CSS_SELECTOR,selector) if x.is_displayed() and x.is_enabled()),False))
  self.mark(e)
  # The credits table has a fixed first column. For amount buttons, centering
  # vertically alone can leave the target beneath that fixed column.
  if selector.startswith('#credits-table [data-year='):
   self.driver.execute_script('arguments[0].scrollIntoView({block:"center",inline:"center"})',e)
  else:self.driver.execute_script('arguments[0].scrollIntoView({block:"center"})',e)
  e.click();self.wait()
 def choose(self,id,value):
  e=self.driver.find_element(By.ID,id);self.mark(e);Select(e).select_by_value(str(value));self.wait()
 def type(self,id,text):
  e=self.driver.find_element(By.ID,id);self.mark(e);e.clear();e.send_keys(text);self.wait()
 def params(self):return parse_qs(urlsplit(self.driver.current_url).query,keep_blank_values=True)
 def home(self):self.driver.get(self.a.url+'/?start=2024&end=2024&measure=CP&budget=BG&base=2025');self.wait()
 def nav(self,name):
  self.click(('[data-pilot="'+name+'"]') if name in ('ecologie','maprimerenov') else '[data-view="'+name+'"]')
  view='credits' if name in ('ecologie','maprimerenov') else name
  assert self.driver.find_element(By.ID,view+'-view').is_displayed(),name
  active=self.driver.find_elements(By.CSS_SELECTOR,'.nav button[aria-current="page"]');assert len(active)==1
  assert (active[0].get_attribute('data-pilot') or active[0].get_attribute('data-view'))==name
 def case(self,name,fn):
  if getattr(self.a,'resume',None) and not name.startswith('Arbre complet ') and any(r['name']==name and r['status']=='ok' for r in self.rows):
   return
  start=time.monotonic()
  try:fn();row=dict(name=name,status='ok',seconds=round(time.monotonic()-start,1))
  except LookupError as e:row=dict(name=name,status='non_execute',detail=str(e))
  except Exception as e:
   row=dict(name=name,status='echec',detail=str(e),action=self.last_action,traceback=traceback.format_exc(),seconds=round(time.monotonic()-start,1))
   try:self.driver.save_screenshot(str(self.out/(str(len(self.rows)+1)+'-echec.png')))
   except Exception:pass
  self.rows=[r for r in self.rows if r['name']!=name];self.rows.append(row);self.save();print(datetime.datetime.now().strftime('%H:%M:%S'),row['status'],name,flush=True)
 def setup(self):
  if urlsplit(self.a.url).hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('Ce lanceur est réservé au local pour ne pas charger le site public.')
  if self.a.serve:
   port=urlsplit(self.a.url).port
   try:urllib.request.urlopen(self.a.url+'/healthz',timeout=2)
   except Exception:
    # Same read-only local preview; only its listening port is changed in memory.
    code="from pathlib import Path; p=Path("+repr(str(ROOT/'tools/preview_workbooks.py'))+"); s=p.read_text(encoding='utf-8').replace(\"(('127.0.0.1',8552),PreviewHandler)\",\"(('127.0.0.1',"+str(port)+"),PreviewHandler)\"); exec(compile(s,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})"
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'.runtime/python-libs')+os.pathsep+str(ROOT);env['BUDGET_DATA_DIR']=str(ROOT/'reports/integration-annexes-20260928/data')
    log=(self.out/'local-server.log').open('ab');self.server=subprocess.Popen([sys.executable,'-u','-c',code],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));log.close()
    for _ in range(40):
     try:urllib.request.urlopen(self.a.url+'/healthz',timeout=1);break
     except Exception:time.sleep(.25)
   with urllib.request.urlopen(self.a.url+'/assets/explorer.js',timeout=10) as r:
    if r.read()!=(ROOT/'public/assets/explorer.js').read_bytes():raise ValueError('Le serveur local ne sert pas la version courante. Utiliser un autre port.')
  options=webdriver.ChromeOptions();options.binary_location='C:/Program Files/Google/Chrome/Application/chrome.exe'
  if not self.a.visible:options.add_argument('--headless=new')
  options.add_argument('--window-size=1440,1000');options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
  options.add_experimental_option('prefs',{'download.default_directory':str(self.downloads),'download.prompt_for_download':False})
  self.driver=webdriver.Chrome(options=options);self.driver.set_page_load_timeout(100)
  self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',{'source':"window.__navCheck={pending:0};const f=window.fetch;window.fetch=(...args)=>{__navCheck.pending++;return f(...args).finally(()=>__navCheck.pending--);};"})
 def returns(self,origin,target):self.home();self.nav(origin);self.nav(target)
 def topic_return(self,origin):
  self.home();self.nav(origin);self.choose('topic','maprimerenov');assert 'MaPrimeRénov' in self.driver.find_element(By.ID,'page-title').text
  self.choose('topic','');assert self.params().get('scope')==[''];assert self.params().get('topic')==[''];assert self.driver.find_element(By.CSS_SELECTOR,'[data-view="credits"]').get_attribute('aria-current')=='page'
 def filters(self):
  self.home()
  for budget in ('BA','CAS','CCF','BG'):self.choose('budget',budget);assert self.params()['budget']==[budget]
  for measure in ('AE','CP'):self.click('[data-measure="'+measure+'"]');assert self.params()['measure']==[measure]
  for id,value in [('start',2023),('end',2025),('start',2024),('end',2024)]:self.choose(id,value);assert self.params()[id]==[str(value)]
  self.click('#constant');assert self.params()['constant']==['1'];self.choose('base',2020);self.click('#constant');assert self.params()['constant']==['0']
  for unit in ('1','1000000','1000000000'):self.choose('unit',unit)
 def modes(self):
  self.home()
  for mode in ('series','ratios','evolution','compare'):
   self.click('[data-mode="'+mode+'"]');assert self.driver.find_element(By.CSS_SELECTOR,'[data-mode="'+mode+'"]').get_attribute('class').find('active')>=0
   if mode in ('series','evolution'):
    for value in [x.get_attribute('value') for x in Select(self.driver.find_element(By.ID,'stage')).options]:self.choose('stage',value)
   if mode=='ratios':
    for value in [x.get_attribute('value') for x in Select(self.driver.find_element(By.ID,'denominator')).options]:self.choose('denominator',value)
 def toggle(self):
  self.home();buttons=self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-exclude]')
  if not buttons:raise LookupError('Aucun poste excluable dans cette sélection')
  ident=buttons[0].get_attribute('data-exclude');self.click('[data-exclude="'+ident+'"]');assert ident in json.loads(self.params()['exclude'][0]);self.click('[data-restore="'+ident+'"]');assert ident not in json.loads(self.params()['exclude'][0])
 def ecology(self):
  self.home();self.nav('ecologie');self.click('[data-ecology-preset="selected"]');assert self.driver.find_element(By.ID,'exclude-count').text=='3'
  for ident in ('TA/345','TA/235'):
   selector='[data-exclude="'+ident+'"],[data-restore="'+ident+'"]';self.click(selector);assert ident not in json.loads(self.params()['exclude'][0]);self.click(selector);assert ident in json.loads(self.params()['exclude'][0])
  self.click('[data-toggle-topic]');assert self.params()['topic']==[''];self.click('[data-toggle-topic]');assert self.params()['topic']==['maprimerenov'];self.click('[data-ecology-preset="full"]');assert self.driver.find_element(By.ID,'exclude-count').text=='0'
 def hierarchy(self):
  self.home();visited=[]
  for depth in range(4):
   candidates=[e for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-scope]') if e.is_enabled()]
   if not candidates:break
   scope=candidates[0].get_attribute('data-scope');self.click('#credits-table [data-scope="'+scope+'"]');assert self.params()['scope']==[scope];visited.append(scope)
  self.click('#breadcrumbs [data-scope=""]');assert self.params()['scope']==[''];assert visited
 def proofs(self):
  self.home();self.nav('maprimerenov');self.click('#credits-table [data-year="2024"][data-stage="EXEC"]');WebDriverWait(self.driver,45).until(lambda d:d.find_elements(By.CSS_SELECTOR,'#source-content .source-card'))
  links=self.driver.find_elements(By.CSS_SELECTOR,'#source-content a');checked=0
  import re
  for link in links:
   m=re.search(r'(?:PDF\s*(?:p\.|à la page)?|Page PDF|PDF à la page)\s*(\d+)',link.text)
   if m:assert urlsplit(link.get_attribute('href')).fragment=='page='+m[1],link.text;checked+=1
  self.click('#close-source');assert not self.driver.find_element(By.ID,'source-dialog').is_displayed()
  if not checked:raise LookupError('Pas de citation PDF paginée dans ce témoin ; les autres sources restent consultables')
 def saved(self):
  self.home();self.click('#save');self.click('[data-saved]');assert self.params()['start']==['2024'];self.click('[data-delete-saved]');assert not self.driver.find_elements(By.CSS_SELECTOR,'[data-saved]')
 def search_rows(self):
  self.home();self.type('row-search','écologie');assert 'Écologie' in self.driver.find_element(By.ID,'credits-table').text;self.type('row-search','')
 def documents(self):
  self.home();self.nav('documents');self.choose('doc-year',2024);self.choose('doc-format','pdf');self.type('doc-search','écologie');time.sleep(.4);self.wait()
  assert self.driver.find_elements(By.CSS_SELECTOR,'.document')
  for mode in ('text','hybrid','title'):self.click('[data-doc-mode="'+mode+'"]')
  self.choose('doc-year','');self.type('doc-search','');time.sleep(.4);self.wait()
  e=self.driver.find_element(By.ID,'more-docs')
  if e.is_displayed():before=len(self.driver.find_elements(By.CSS_SELECTOR,'.document'));self.click('#more-docs');assert len(self.driver.find_elements(By.CSS_SELECTOR,'.document'))>before
 def exports(self):
  self.home()
  for fmt,suffix in [('csv','.csv'),('xlsx','.xlsx'),('selection','.json')]:
   self.choose('export-format',fmt);before=set(self.downloads.iterdir());self.click('#export')
   files=WebDriverWait(self.driver,90).until(lambda d:[p for p in set(self.downloads.iterdir())-before if p.suffix==suffix and p.stat().st_size])
   p=files[0]
   if fmt=='xlsx':assert zipfile.is_zipfile(p)
   elif fmt=='selection':assert {'parameters','rows','totals'} <= json.loads(p.read_text(encoding='utf-8')).keys()
   else:assert 'Montant' in p.read_text(encoding='utf-8-sig')
 def mobile(self):
  self.driver.set_window_size(390,844);self.home();assert self.driver.execute_script('return document.documentElement.scrollWidth <= innerWidth+1')
  self.nav('maprimerenov');self.choose('topic','');assert self.params()['topic']==[''];self.driver.set_window_size(1440,1000)
 def matrix(self,budget,year,measure):
  self.driver.get(self.a.url+f'/?start={year}&end={year}&budget={budget}&measure={measure}&base=2025');self.wait()
  assert self.params()['budget']==[budget];assert self.params()['start']==[str(year)];assert self.params()['measure']==[measure]
 def branch(self,budget,scope):
  self.matrix(budget,2024,'CP');self.click('#credits-table [data-scope="'+scope+'"]')
  children=[e.get_attribute('data-scope') for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-scope]') if e.is_enabled()]
  for child in children:
   self.click('#credits-table [data-scope="'+child+'"]');assert self.params()['scope']==[child]
   deeper=[e.get_attribute('data-scope') for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-scope]') if e.is_enabled()]
   if deeper:self.click('#credits-table [data-scope="'+deeper[0]+'"]');assert self.params()['scope']==[deeper[0]]
   self.click('#breadcrumbs [data-scope="'+scope+'"]');assert self.params()['scope']==[scope]
  self.click('#breadcrumbs [data-scope=""]');assert self.params()['scope']==['']
 def server_error(self):
  self.home()
  self.driver.execute_script("const original=window.fetch;window.fetch=(url,...rest)=>{if(String(url).startsWith('/api/explorer?')){window.fetch=original;return Promise.resolve(new Response('<html>Bad Gateway</html>',{status:502,headers:{'Content-Type':'text/html'}}));}return original(url,...rest);};load();")
  WebDriverWait(self.driver,10).until(lambda d:d.find_element(By.ID,'error').is_displayed())
  text=self.driver.find_element(By.ID,'error').text;assert '502' in text and 'JSON' not in text and 'Unexpected token' not in text
  WebDriverWait(self.driver,10).until(lambda d:d.find_element(By.ID,'request-progress').get_attribute('hidden') is not None)
  self.click('#reset');assert not self.driver.find_element(By.ID,'error').is_displayed()
 def loading_indicator(self):
  self.home()
  self.driver.execute_script("const original=window.fetch;window.fetch=(url,...rest)=>{if(String(url).startsWith('/api/explorer?')){window.fetch=original;return new Promise(resolve=>setTimeout(resolve,1500)).then(()=>original(url,...rest));}return original(url,...rest);};load();")
  assert self.driver.find_element(By.ID,'request-progress').is_displayed();self.wait();assert not self.driver.find_element(By.ID,'request-progress').is_displayed()
 def rapid_changes(self):
  self.home()
  self.driver.execute_script("for(const value of ['2017','2020','2023']){const e=document.getElementById('start');e.value=value;e.dispatchEvent(new Event('change',{bubbles:true}));}")
  self.wait();assert self.params()['start']==['2023'];assert self.driver.find_element(By.ID,'start').get_attribute('value')=='2023'
 def extra_controls(self):
  self.home();self.nav('ecologie');self.click('[data-ecology-preset="selected"]');self.click('[data-topic-exclusion-details]');self.click('#close-source')
  self.home();self.choose('start',2023);self.click('[data-mode="evolution"]');self.click('[data-evolution]');assert self.driver.find_element(By.ID,'source-dialog').is_displayed();self.click('#close-source')
  self.home();self.nav('maprimerenov');self.click('summary');self.choose('topic_mode','without');self.choose('topic_mode','only')
  self.proofs()
 def run(self):
  try:
   self.setup()
   self.case('Chargement initial',self.home)
   if self.a.phase=='all':
    for origin in NAV:
     for target in NAV:
      if origin!=target:self.case('Navigation '+origin+' → '+target,lambda o=origin,t=target:self.returns(o,t))
    for origin in NAV:self.case('Menu Grand dossier aller-retour depuis '+origin,lambda o=origin:self.topic_return(o))
    for name,fn in [('Filtres et unités',self.filters),('Modes et étapes du tableau',self.modes),('Exclusion et réintégration',self.toggle),('Trois exclusions Écologie',self.ecology),('Descente et retour dans les postes',self.hierarchy),('Preuves et pages PDF',self.proofs),('Sélections enregistrées',self.saved),('Recherche dans les lignes',self.search_rows),('Bibliothèque et modes de recherche',self.documents),('Trois formats exportés',self.exports),('Navigation mobile',self.mobile)]:self.case(name,fn)
    self.case('Réinitialiser',lambda:(self.home(),self.click('#reset')))
   self.case('Réponse HTML en erreur et reprise',self.server_error)
   self.case('Roue pendant une réponse lente',self.loading_indicator)
   self.case('Sélections rapides : dernier choix conservé',self.rapid_changes)
   self.case('Explications et liens des montants',self.extra_controls)
   if self.a.intensive:
    for budget in ('BG','BA','CAS','CCF'):
     for year in range(2017,2027):
      for measure in ('AE','CP'):self.case(f'Matrice {budget} {year} {measure}',lambda b=budget,y=year,m=measure:self.matrix(b,y,m))
    if not getattr(self.a,'full_controls',False):
     for budget in ('BG','BA','CAS','CCF'):
      self.matrix(budget,2024,'CP')
      roots=self.driver.execute_script('return data.rows.filter(r=>r.has_children).map(r=>r.id)')
      # DOM is authoritative for navigation: API field names need not encode children.
      roots=[e.get_attribute('data-scope') for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-scope]') if e.is_enabled()]
      for scope in roots:self.case('Arbre '+budget+' '+scope,lambda b=budget,s=scope:self.branch(b,s))
   if getattr(self.a,'check_documents',False):self.case('Disponibilité du catalogue documentaire',self.linked_documents)
   if getattr(self.a,'full_controls',False):
    self.case('Boutons, explications et paginations',self.remaining_controls)
    self.case('Recherche et ouverture des passages',self.document_search_buttons)
    self.combined_filters();self.complete_tree()
   if getattr(self.a,'check_documents',False):self.case('Tous les documents et liens rencontrés',self.linked_documents)
   logs=[r for r in self.driver.get_log('browser') if r['level']=='SEVERE' and 'favicon' not in r['message']]
   (self.out/'browser-errors.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
   if logs:self.rows.append(dict(name='Console du navigateur',status='echec',detail=str(len(logs))+' messages à examiner dans browser-errors.json'))
   if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected for name,expected in self.source_signature.items()):self.rows.append(dict(name='Version contrôlée',status='echec',detail='Les fichiers du site ont changé pendant le contrôle. Refaire un contrôle sur une version stable.'))
   self.finished=True
  except KeyboardInterrupt:self.rows.append(dict(name='Interruption utilisateur',status='non_execute',detail='Résultats déjà enregistrés conservés.'))
  except Exception as e:self.rows.append(dict(name='Démarrage',status='echec',detail=str(e),traceback=traceback.format_exc()))
  finally:
   result=self.save()
   if self.driver:self.driver.quit()
   if self.server:self.server.terminate();self.server.wait(timeout=15)
   print('RAPPORT : '+str(self.out/'rapport.html'),flush=True)
  return 0 if result['complete'] else 1 if result['failed'] else 2
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18566');p.add_argument('--serve',action='store_true');p.add_argument('--visible',action='store_true');p.add_argument('--intensive',action='store_true');p.add_argument('--full-controls',action='store_true');p.add_argument('--check-documents',action='store_true');p.add_argument('--phase',choices=['all','extended'],default='all');p.add_argument('--resume',type=Path);args=p.parse_args();sys.exit(Check(args).run())
