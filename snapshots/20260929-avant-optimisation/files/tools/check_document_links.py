"""Check link availability and file signatures, never the facts in documents."""
import html,json,time,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,urljoin

def target_url(url):
 u=urlsplit(url)
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('Lien HTTP(S) invalide')
 return urlunsplit((u.scheme,u.netloc,u.path,u.query,''))

def probe(url,expected=None,timeout=20):
 started=time.monotonic();result={'url':url,'status':'non_verifie','format':expected}
 try:
  url=target_url(url)
  headers={'User-Agent':'NosDeniers-FunctionalLinkCheck/1.0','Range':'bytes=0-1023','Accept-Encoding':'identity'}
  # Read only the beginning, not the entire PDF. Never submit forms or follow mailto.
  with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=timeout) as response:
   body=response.read(1024);kind=response.headers.get('Content-Type','').lower()
   result.update(http=response.status,final_url=response.url,content_type=kind,bytes_inspected=len(body))
   if not body:raise ValueError('Réponse vide')
   pdf=expected=='pdf' or urlsplit(response.url).path.lower().endswith('.pdf') or 'application/pdf' in kind
   if pdf and b'%PDF-' not in body:raise ValueError('Le lien PDF renvoie un autre contenu, souvent une page HTML')
   if expected in ('xlsx','ods','zip') and not body.startswith(b'PK'):raise ValueError('Le lien ne renvoie pas le fichier bureautique attendu')
   # No XLS signature assertion: some public .xls files are legitimate HTML tables.
   result['status']='accessible';result['detail']='Réponse non vide'+(' ; signature PDF reconnue' if pdf else '')
 except urllib.error.HTTPError as e:
  result.update(http=e.code,status='introuvable' if e.code in (404,410) else 'non_verifie',detail='HTTP '+str(e.code));e.close()
 except ValueError as e:result.update(status='defaut',detail=str(e))
 except Exception as e:result.update(detail=str(e))
 result['seconds']=round(time.monotonic()-started,2);return result

def run(base,out,links,delay=.4,catalogue=True,limit=None):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);records={};targets={};fragments=[]
 if catalogue:
  with urllib.request.urlopen(base+'/api/documents?format=',timeout=45) as response:items=json.load(response)['items']
  for item in items:
   url=base+'/api/download/'+str(item['id']);targets[url]={'format':item.get('format'),'label':item.get('title',''),'kind':'document local ou miroir public'}
   if item.get('url'):
    try:targets.setdefault(target_url(item['url']),{'format':None,'label':item.get('title',''),'kind':'source officielle'})
    except ValueError:fragments.append({'url':item['url'],'status':'defaut','detail':'Adresse source invalide'})
 for link in links.values():
  url=link['url'];u=urlsplit(url)
  if link.get('raw') in ('','#'):
   fragments.append({'url':url,'status':'defaut','detail':'Lien sans destination','label':link.get('label','')});continue
  if u.scheme not in ('http','https'):
   fragments.append({'url':url,'status':'non_verifie','detail':'Action externe à vérifier manuellement : '+u.scheme,'label':link.get('label','')});continue
  if u.fragment.startswith('page=') and (not u.fragment[5:].isdigit() or int(u.fragment[5:])<1):fragments.append({'url':url,'status':'defaut','detail':'Repère PDF invalide'})
  targets.setdefault(target_url(url),{'format':'pdf' if u.fragment.startswith('page=') else None,'label':link.get('label',''),'kind':'lien rencontré dans une page'})
 # These checks only read resources. Skip state-changing or unsupported URI schemes.
 plan=list(targets.items())
 if limit is not None:plan=plan[:limit]
 blocked={};refusals={}
 log=out/'liens.jsonl'
 if log.exists():
  for line in log.read_text(encoding='utf-8').splitlines():
   try:r=json.loads(line);records[r['url']]=r
   except ValueError:pass
  # Preserve a torn final record without attaching the next JSON object to it.
  with log.open('rb+') as f:
   f.seek(0,2)
   if f.tell():
    f.seek(-1,2)
    if f.read(1)!=b'\n':f.seek(0,2);f.write(b'\n')
  for r in records.values():
   host=urlsplit(r['url']).netloc
   if r.get('http') in (401,403,429,500,502,503,504):
    refusals[host]=refusals.get(host,0)+1
    if refusals[host]>=3:blocked[host]=True
   elif r['status']=='accessible':refusals[host]=0
 def save(finished=False):
  values=list(records.values())+fragments;errors=[r for r in values if r['status'] in ('introuvable','defaut')];unknown=[r for r in values if r['status']=='non_verifie']
  summary=dict(finished=finished,planned=len(targets),checked=len(records),accessible=sum(r['status']=='accessible' for r in values),broken=len(errors),unverified=len(unknown),limited=limit is not None,scope='Disponibilité HTTP et signature de fichier. Aucun contrôle des chiffres ni du contenu documentaire. Les documents absents localement peuvent être vérifiés sur leur miroir public.')
  (out/'bilan.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
  lines=''.join('<tr><td>'+html.escape(r.get('label',''))+'</td><td>'+html.escape(r['status'])+'</td><td>'+html.escape(r.get('detail',''))+'</td><td>'+html.escape(r['url'])+'</td></tr>' for r in values if r['status']!='accessible')
  (out/'rapport-liens.html').write_text('<!doctype html><meta charset="utf-8"><title>Disponibilité des documents</title><style>body{font:16px system-ui;color:#163b52;margin:35px}td,th{padding:10px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}table{width:100%;table-layout:fixed}</style><h1>Documents et liens</h1><p>'+html.escape(str(summary['checked']))+' liens contrôlés / '+str(summary['planned'])+' prévus · '+str(summary['broken'])+' défauts · '+str(summary['unverified'])+' non vérifiés.</p><p>'+html.escape(summary['scope'])+'</p><p>'+('Terminé.' if finished else 'Contrôle en cours ou interrompu. Les résultats sont conservés.')+'</p><table><tr><th>Document</th><th>État</th><th>Explication</th><th>Adresse</th></tr>'+lines+'</table>',encoding='utf-8')
  return summary
 save()
 try:
  with log.open('a',encoding='utf-8') as f:
   for i,(url,meta) in enumerate(plan):
    if url in records:continue
    host=urlsplit(url).netloc
    result=dict({'url':url,'status':'non_verifie','detail':'Vérification différée après plusieurs refus ou erreurs du même serveur'} if host in blocked else probe(url,meta['format']),**meta)
    if result.get('http') in (401,403,429,500,502,503,504):
     refusals[host]=refusals.get(host,0)+1
     if refusals[host]>=3:blocked[host]=True
    elif result['status']=='accessible':refusals[host]=0
    records[url]=result;f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
    if i%20==0:save();print(time.strftime('%H:%M:%S'),'Liens',len(records),'/',len(targets),flush=True)
    time.sleep(delay)
 finally:summary=save(len(records)==len(targets))
 return summary
