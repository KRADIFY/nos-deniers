"""Extended functional scenarios. No budget changes or source-content analysis."""
import json,time
from urllib.parse import urlencode
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select,WebDriverWait
class ExpandedControls:
 def modal_check(self,selector):
  self.click(selector)
  dialog=self.driver.find_element(By.ID,'source-dialog');assert dialog.is_displayed(),'Fenêtre absente'
  content=self.driver.find_element(By.ID,'source-content').text.strip()
  assert content and content!='Lecture des sources…','Fenêtre sans réponse'
  assert not any(t in content for t in ('Unexpected token','réponse du serveur est illisible','Connexion interrompue','HTTP 502','HTTP 504','Passage indisponible')),'Fenêtre en erreur : '+content[:180]
  # Expand the explanations so that their document and contact links are inventoried.
  for _ in range(20):
   closed=[e for e in self.driver.find_elements(By.CSS_SELECTOR,'#source-content details:not([open]) > summary') if e.is_displayed()]
   if not closed:break
   self.mark(closed[0]);closed[0].click()
  self.inventory()
  copies=[e for e in self.driver.find_elements(By.CSS_SELECTOR,'[data-copy-quality]') if e.is_displayed()]
  if copies:
   self.mark(copies[0]);copies[0].click();assert self.driver.find_element(By.ID,'quality-request').get_attribute('value')
  self.click('#close-source');assert not dialog.is_displayed();self.proofs_checked+=1
  with (self.out/'fenetres-verifiees.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps({'selector':selector,'page':self.driver.current_url,'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S')},ensure_ascii=False)+'\n')
  if self.proofs_checked%20==0:self.save();print(time.strftime('%H:%M:%S'),'Fenêtres de preuve vérifiées',self.proofs_checked,flush=True)
 def remaining_controls(self):
  self.home();self.nav('maprimerenov')
  examples=[e.get_attribute('data-topic-example') for e in self.driver.find_elements(By.CSS_SELECTOR,'[data-topic-example]')]
  for example in examples:
   self.home();self.nav('maprimerenov');self.click('[data-topic-example="'+example+'"]');assert self.driver.find_element(By.ID,'credits-view').is_displayed()
  self.home();self.choose('topic','maprimerenov');self.choose('topic_mode','without');self.click('[data-restore-topic]');assert self.params()['topic']==['']
  self.home();self.nav('movements')
  explanations=[e.get_attribute('data-rap-explanation') for e in self.driver.find_elements(By.CSS_SELECTOR,'[data-rap-explanation]') if e.is_displayed()]
  for key in explanations:self.modal_check('[data-rap-explanation="'+key+'"]')
  for _ in range(30):
   more=self.driver.find_element(By.ID,'rap-movements-more')
   if not more.is_displayed():break
   before=len(self.driver.find_elements(By.CSS_SELECTOR,'#rap-movements-table tbody tr'));self.click('#rap-movements-more');assert len(self.driver.find_elements(By.CSS_SELECTOR,'#rap-movements-table tbody tr'))>before
  else:raise AssertionError('Pagination des mouvements non terminée en 30 clics')
  self.home();self.nav('documents');self.choose('doc-year','');self.choose('doc-format','');self.type('doc-search','')
  for _ in range(200):
   if not self.driver.find_element(By.ID,'more-docs').is_displayed():break
   before=len(self.driver.find_elements(By.CSS_SELECTOR,'.document'));self.click('#more-docs');assert len(self.driver.find_elements(By.CSS_SELECTOR,'.document'))>before
  else:raise AssertionError('Pagination documentaire non terminée en 200 clics')
 def document_search_buttons(self):
  self.home();self.nav('documents')
  for mode in ('text','hybrid'):
   self.click('[data-doc-mode="'+mode+'"]');self.type('doc-search','rénovation énergétique');self.click('#doc-submit')
   passages=[e for e in self.driver.find_elements(By.CSS_SELECTOR,'[data-passage]') if e.is_displayed()]
   if passages:self.modal_check('[data-passage]')
   else:
    text=self.driver.find_element(By.ID,'documents').text
    assert text.strip(),'Recherche sans résultat ni explication'
    if 'indisponible' in text.lower():raise LookupError('Service '+mode+' indisponible : parcours de résultats non vérifié')
 def combined_filters(self):
  # Every pair of dimensions in this deterministic grid appears in a scenario.
  import itertools
  domains={'budget':['BG','BA','CAS','CCF'],'measure':['AE','CP'],'period':[(2017,2018),(2021,2024),(2025,2026)],'constant':[False,True],'base':[2017,2025],'topic':['','maprimerenov'],'topic_mode':['only','without']}
  keys=list(domains);candidates=[dict(zip(keys,values)) for values in itertools.product(*(domains[k] for k in keys))]
  candidates=[c for c in candidates if (not c['topic'] or c['budget']=='BG') and (c['topic'] or c['topic_mode']=='only')]
  def pairs(c):return {(a,repr(c[a]),b,repr(c[b])) for a,b in itertools.combinations(keys,2)}
  remaining=set().union(*(pairs(c) for c in candidates));selected=[]
  while remaining:
   best=max(candidates,key=lambda c:len(pairs(c)&remaining));selected.append(best);remaining-=pairs(best)
  for i,c in enumerate(selected):
   def test(c=c):
    self.home();self.choose('budget',c['budget']);self.choose('start',c['period'][0]);self.choose('end',c['period'][1]);self.click('[data-measure="'+c['measure']+'"]')
    self.choose('topic',c['topic'])
    if c['topic']:self.choose('topic_mode',c['topic_mode'])
    if c['constant']:self.click('#constant');self.choose('base',c['base'])
    for mode in ('series','ratios','evolution','compare'):self.click('[data-mode="'+mode+'"]');assert self.driver.find_element(By.ID,'credits-table').text.strip()
    self.nav('movements');self.nav('credits');assert self.driver.find_element(By.ID,'credits-table').text.strip()
   self.case('Filtres croisés '+str(i+1)+' '+json.dumps(c,ensure_ascii=False),test)
 def complete_tree(self):
  tested_proofs=set()
  # All available paths in the union of 2017-2026, for the 4 budgets and AE/CP.
  # This is not every year interval times every subset of exclusions.
  for budget in ('BG','BA','CAS','CCF'):
   for measure in ('AE','CP'):
    todo=[''];seen=set()
    while todo:
     scope=todo.pop(0)
     if scope in seen:continue
     seen.add(scope);children=[];self.active_scope={'budget':budget,'measure':measure,'scope':scope,'queued':len(todo),'visited':len(seen)};self.save()
     def test():
      query=dict(start=2017,end=2026,budget=budget,measure=measure,scope=scope,base=2025)
      self.driver.get(self.a.url+'/?'+urlencode(query));self.wait()
      children.extend(e.get_attribute('data-scope') for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-scope]') if e.is_enabled())
      # Each enabled include/exclude switch at this node, followed by restoration.
      switches=[e.get_attribute('data-exclude') for e in self.driver.find_elements(By.CSS_SELECTOR,'#credits-table [data-exclude]') if e.is_enabled()]
      for ident in switches:
       selector='[data-exclude="'+ident+'"]';self.click(selector);assert ident in json.loads(self.params()['exclude'][0])
       restore='[data-restore="'+ident+'"]'
       if not any(e.is_displayed() and e.is_enabled() for e in self.driver.find_elements(By.CSS_SELECTOR,restore)):
        restore=selector  # Transverse dossiers use the same sidebar switch in both directions.
       self.click(restore);assert ident not in json.loads(self.params()['exclude'][0])
      self.click('[data-mode="series"]')
      stages=[x.get_attribute('value') for x in Select(self.driver.find_element(By.ID,'stage')).options]
      for stage in stages:
       self.choose('stage',stage)
       buttons=self.driver.execute_script("return [...document.querySelectorAll('#credits-table [data-year]')].map(e=>({year:e.dataset.year,stage:e.dataset.stage,scope:e.dataset.cellScope}))")
       for b in buttons:
        key=(budget,measure,b['year'],b['stage'],b['scope'])
        if key in tested_proofs:continue
        self.modal_check('#credits-table [data-year="'+b['year']+'"][data-stage="'+b['stage']+'"][data-cell-scope="'+b['scope']+'"]');tested_proofs.add(key)
      # The breadcrumb is a real return click, not only a direct URL test.
      if scope:self.click('#breadcrumbs [data-scope=""]');assert self.params()['scope']==['']
     self.case('Arbre complet '+budget+' '+measure+' '+(scope or 'racine'),test)
     todo.extend(c for c in children if c not in seen)
 def linked_documents(self):
  from check_document_links import run
  summary=run(self.a.url,self.out/'documents',self.links)
  self.documents_summary=summary
  if summary['broken']:raise AssertionError(str(summary['broken'])+' liens défectueux ; voir documents/rapport-liens.html')
  if summary['unverified']:raise LookupError(str(summary['unverified'])+' adresses non vérifiées ; voir documents/rapport-liens.html')
