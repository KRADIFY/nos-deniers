"""Resumable read-only source research. Candidates never become numeric facts."""
from pathlib import Path
import concurrent.futures, datetime, hashlib, json, re, sqlite3, urllib.parse, urllib.request
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/mpr-closure-20260920'

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')

def fetch(label, url):
    path = OUT/'connections'/f'{label}.json'
    if path.exists():
        cached=json.loads(path.read_text(encoding='utf8'))
        if not label.startswith('local-') or cached.get('response',{}).get('available'): return cached
    result = {'label': label, 'url': url, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NosDeniers-source-audit/1.0', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=45) as response:
            raw=response.read(12000000)
            result.update(http_status=response.status, content_type=response.headers.get('Content-Type'), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        try: result['response']=json.loads(raw)
        except ValueError: result['preview']=raw[:600].decode('utf8', errors='replace')
    except Exception as exc: result['error']=str(exc)
    dump(path, result)
    return result

def connections():
    urls={
       'bercy-catalog-mpr': 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets?limit=100&where='+urllib.parse.quote('search("renovation")'),
       'bercy-lfi2019-record': 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/loi-de-finances-initiale-pour-2019-lfi-2019/records?limit=2',
       'bercy-catalog-budget': 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets?limit=100&where='+urllib.parse.quote('search("finances")'),
    }
    for q in ['MaPrimeRenov', 'Anah', 'renovation energetique', 'PLF 2026', 'execution budget Etat', 'LFI 2025']:
        urls['datagouv-'+re.sub('[^a-z0-9]+','-',q.lower())]='https://www.data.gouv.fr/api/1/datasets/?'+urllib.parse.urlencode({'q':q,'page_size':100})
    for y in range(2020,2027):
        urls[f'local-hybrid-{y}']='http://127.0.0.1:8552/api/semantic-search?'+urllib.parse.urlencode({'q':'MaPrimeRénov prime transition énergétique financement PLF LFI crédits ouverts AE CP réserve dégel','year':y,'format':'pdf','limit':30})
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(lambda item:fetch(*item),[(k,v) for k,v in urls.items() if not k.startswith('local-')]):
            print(r['label'],r.get('http_status'),r.get('error',''),flush=True)
    for k,v in urls.items():
        if k.startswith('local-'):
            r=fetch(k,v);print(k,r.get('response',{}).get('available'),flush=True)

def local_sources():
    import fitz
    db=sqlite3.connect(Path('D:/LexMachine/NosDeniers/search_20260919/search.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    cat=sqlite3.connect(Path('F:/LexMachine/NosDeniers/generation_tables_20260911/catalogue.sqlite').as_uri()+'?mode=ro',uri=True);cat.row_factory=sqlite3.Row
    docs=db.execute("SELECT * FROM documents WHERE format='pdf' AND (lower(title) LIKE '%renov%' OR lower(title) LIKE '%rénov%' OR lower(title) LIKE '%cohesion%' OR lower(title) LIKE '%cohésion%' OR lower(title) LIKE '%cologie%' OR lower(title) LIKE '%nergie, climat%' OR lower(title) LIKE '%relance%')").fetchall()
    inventory=[]
    for row in docs:
        d=dict(row)
        asset=cat.execute('SELECT * FROM assets WHERE sha256=?',(d['source_sha256'],)).fetchone()
        if not asset: continue
        path=Path(asset['path']);d['physical_path']=str(path)
        if not path.is_absolute(): path=Path('F:/LexMachine/NosDeniers/generation_tables_20260911')/path
        d['physical_path']=str(path)
        key=d['source_id'] or d['source_sha256'][:20]
        target=OUT/'local-pages'/f'{key}.json'
        if target.exists():
            saved=json.loads(target.read_text(encoding='utf8'));inventory.append(saved['document']);continue
        try:
            with fitz.open(path) as pdf:
                texts=[p.get_text() for p in pdf]
            hits=[i for i,t in enumerate(texts) if re.search(r'maprime\s*r[ée]nov|prime de transition|prime transition|mpr\b',t,re.I)]
            d['pages_total']=len(texts);d['matched_pages']=[i+1 for i in hits]
            expanded=sorted({j for i in hits for j in range(max(0,i-1),min(len(texts),i+2))})
            dump(target,{'document':d,'pages':[{'page':i+1,'text':texts[i]} for i in expanded]})
        except Exception as exc:d['read_error']=str(exc)
        inventory.append(d)
    dump(OUT/'local-inventory.json',inventory)
    print('physical_source_inventory',len(inventory), 'matching_pages',sum(len(r.get('matched_pages',[])) for r in inventory),flush=True)

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(connections),pool.submit(local_sources)]
        for f in futures:f.result()
