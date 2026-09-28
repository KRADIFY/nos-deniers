"""Create a content-deduplicated import plan; never edits the live catalogue."""
import collections,hashlib,json,re,unicodedata
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCAN=ROOT/'reports/selenium-budget/scan-2019-2022-cible-20260909'
OUT=ROOT/'reports/import-selenium-2019-2022-20260909'
OUT.mkdir(exist_ok=True)
state=json.loads((SCAN/'state.json').read_text(encoding='utf-8'))
original=json.loads((ROOT/'reports/MANIFEST-COLLECTE.json').read_text(encoding='utf-8'))
records=json.loads(json.dumps(original)); known={r['sha256']:r for r in records if r.get('sha256')}
original_hashes=set(known)
topic_hashes={r['sha256'] for r in json.loads((ROOT/'budget_service/data/maprimerenov.json').read_text(encoding='utf-8'))['sources']}
now=datetime.now(timezone.utc).isoformat(); items=[];new=[];uncertain=[];matches=[]

def metadata(item):
    name=item['filename']; upper=name.upper(); head=item.get('head_text','')
    # Exercise embedded in official filename is stronger than a publication date.
    m=re.search(r'(20\d{2})',name)
    year=m.group(1) if m else None
    if not year:
        years=set()
        for page in item.get('source_pages',[]):
            matches=re.findall(r'exercice-(20\d{2})',page)
            if matches:years.add(matches[-1])
        if len(years)==1:year=years.pop()
    if not year:
        m=re.search(r'\b(?:PLF|PLR|PLRG|RAP|PAP)\s*(20\d{2})\b',head[:1500])
        if m:year=m.group(1)
    context=item.get('context','')
    stage=('rap' if re.search(r'PLR|RAP',upper) else 'pap' if 'PAP' in upper else
           'plf' if 'PLF' in upper else 'lfi' if 'LFI' in upper else
           'jaune' if 'JAUNE' in upper else 'dpt' if 'DPT' in upper else 'annexes')
    if stage=='annexes':
        for token,value in [('RAP','rap'),('PAP','pap'),('Jaunes','jaune'),('DPT','dpt'),('PLF','plf'),('LFI','lfi')]:
            if re.search(r'\b'+token+r'\b',context):stage=value;break
    title=item.get('title') or Path(name).stem.replace('_',' ')
    title=f"{stage.upper()} {year or 'année à confirmer'} — {title}"
    return year,stage,title

for url,item in state['documents'].items():
    if item['status']=='matched_filename':
        if not any(r['path']==item['path'] and r.get('sha256')==item.get('sha256') for r in original):
            raise ValueError('Filename match no longer in manifest: '+url)
        matches.append({'url':url,'path':item['path'],'sha256':item['sha256'],'basis':'filename against previously validated catalogue'})
        continue
    if item['status'] not in {'downloaded','duplicate','already_present'}:raise ValueError('Unresolved document '+url)
    if not item.get('local_path'):continue
    path=Path(item['local_path']).resolve()
    if not path.is_relative_to(SCAN/'downloads'):raise ValueError('File outside incoming download folder')
    if not path.is_file() or path.stat().st_size!=item['bytes']:raise ValueError('File missing or size differs')
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    if sha!=item['sha256']:raise ValueError('File changed after validation')
    if sha in topic_hashes:raise ValueError('Topic reconciliation required')
    old=known.get(sha)
    if old:
        record=old;kind='already_present' if sha in original_hashes else 'duplicate_in_batch'
    else:
        year,stage,title=metadata(item)
        if not year:uncertain.append({'url':url,'filename':item['filename']})
        slug=unicodedata.normalize('NFKD',Path(item['filename']).stem).encode('ascii','ignore').decode()
        slug=re.sub('[^A-Za-z0-9_-]+','-',slug).strip('-')[:110]
        record={'path':f"public/selenium/{stage}/{year or 'annee-a-confirmer'}/{slug}-{sha[:12]}.{item['format']}",
                'title':title,'years_title':[year] if year else [],'format':item['format'],'role':'official_document',
                'status':'downloaded','checked_at':now,'bytes':item['bytes'],'sha256':sha,'pages':item.get('pages'),
                'text_extractable':bool(item.get('head_text','').strip()),'original_filename':item['filename'],
                'provenance':'Catalogue budget.gouv.fr, téléchargement Selenium et validation locale',
                'url':url,'url_match':'official_download_link','source_pages':item.get('source_pages',[]),
                'import_batch':'selenium-2019-2022-20260909','numeric_import':False}
        records.append(record);new.append(record);known[sha]=record;kind='new'
    if url not in record.setdefault('collection_urls',[]):record['collection_urls'].append(url)
    if item['filename'] not in record.setdefault('collection_aliases',[]):record['collection_aliases'].append(item['filename'])
    items.append({'filename':path.relative_to(SCAN/'downloads').as_posix(),'path':record['path'],
                  'sha256':sha,'bytes':item['bytes'],'disposition':kind})

summary={'dispositions':dict(collections.Counter(x['disposition'] for x in items)),
         'new_years':dict(collections.Counter(','.join(r['years_title']) or 'unknown' for r in new)),
         'new_formats':dict(collections.Counter(r['format'] for r in new)),
         'new_bytes':sum(r['bytes'] for r in new),'old_sources':len(original),'new_sources':len(records),
         'filename_matches':len(matches),'uncertain_metadata':len(uncertain)}
plan={'at':now,'base_manifest_sha256':hashlib.sha256((ROOT/'reports/MANIFEST-COLLECTE.json').read_bytes()).hexdigest(),
      'items':items,'new_records':new,'summary':summary}
for name,value in [('plan.json',plan),('manifest-merged.json',records),('filename-matches.json',matches),('uncertain-metadata.json',uncertain)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
print(json.dumps(uncertain,ensure_ascii=False))
