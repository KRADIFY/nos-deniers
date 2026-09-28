"""Add the two requested dossier shortcuts, preserving shared analysis filters."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/reserves-et-consignes-20260909'
BACKUP=OUT/'avant-onglets'
BACKUP.mkdir(parents=True,exist_ok=True)
paths=['public/explorer.html','public/assets/explorer.js']
before={p:(ROOT/p).read_bytes() for p in paths}
for p,raw in before.items():
    dest=BACKUP/Path(p).name
    if not dest.exists():dest.write_bytes(raw)

html=before[paths[0]].decode('utf-8')
marker=' <button type="button" data-view="movements">'
assert html.count(marker)==1 and 'data-pilot=' not in html
html=html.replace(marker,
    ' <button type="button" data-pilot="ecologie">Mission Écologie</button>\n'
    ' <button type="button" data-pilot="maprimerenov">MaPrimeRénov’</button>\n'+marker)

js=before[paths[1]].decode('utf-8')
nav="document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===next);if(b.dataset.view===next)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});"
heading="$('page-title').textContent=labels[next][0];$('subtitle').textContent=labels[next][1];"
assert nav in js and heading in js
js=js.replace(heading+nav,'renderNavigation();')
new="""function currentPilot(){
 if(state.budget!=='BG')return '';
 if(state.topic==='maprimerenov'&&state.topic_mode==='only')return 'maprimerenov';
 if(state.scope==='TA'||state.scope.startsWith('TA/'))return 'ecologie';
 return '';
}
function renderNavigation(){
 const pilot=view==='credits'?currentPilot():'';
 const title=pilot==='ecologie'?'Mission Écologie.':pilot==='maprimerenov'?'MaPrimeRénov’.':labels[view][0];
 $('page-title').textContent=title;$('subtitle').textContent=labels[view][1];
 document.querySelectorAll('.nav button').forEach(b=>{
  const active=pilot?b.dataset.pilot===pilot:b.dataset.view===view;
  b.classList.toggle('active',active);
  if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
 });
}
async function openPilot(pilot){
 state={...state,budget:'BG',scope:pilot==='ecologie'?'TA':'',topic:pilot==='maprimerenov'?'maprimerenov':'',topic_mode:'only',exclude:[]};
 $('row-search').value='';sync();setView('credits');await load();
}
"""
js=js.replace('function setView(next){',new+'function setView(next){')
js=js.replace('function render(){if(!data)return;','function render(){if(!data)return;\n renderNavigation();')
js=js.replace(' if(b.dataset.view)setView(b.dataset.view);',' if(b.dataset.view)setView(b.dataset.view);\n if(b.dataset.pilot)openPilot(b.dataset.pilot);')
for p,content in [(paths[0],html),(paths[1],js)]:
    (ROOT/p).write_bytes(content.encode('utf-8'))
(OUT/'onglets-changements.json').write_text(json.dumps(dict(
    files=[dict(path=p,before_sha256=hashlib.sha256(before[p]).hexdigest(),after_sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in paths],
    change='Deux accès directs Mission Écologie et MaPrimeRénov’. Années, AE/CP, inflation, unité et mode de tableau conservés. Périmètre et exclusions remis à ceux du dossier choisi.',
    public_deployment=False, numeric_data_changed=False,css_changed=False),ensure_ascii=False,indent=2),encoding='utf-8')
print('Two pilot shortcuts added; original files backed up.')
