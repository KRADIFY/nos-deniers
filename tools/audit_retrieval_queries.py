"""Resumable discovery audit; findings are documentary candidates, never facts."""
import json,time,hashlib,urllib.request,urllib.parse
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/finalisation-20260919/retrieval-audit'
OUT.mkdir(parents=True,exist_ok=True)
queries=[]
for year in range(2020,2027):
    queries.extend([(str(year),'MaPrimeRénov crédits AE CP LFI consommation'),(str(year),'MaPrimeRénov programme 174 135 prime transition énergétique')])
queries.extend([('2026','projet loi finances crédits mission écologie autorisations engagement paiement'),('2025','mise en réserve surgel dégel programme 135 rénovation'),('2024','réserve précaution annulations justice'),('2025','réserve précaution dégels défense'),('2024','fonds concours attributions produits rattachements'),('2023','reports crédits non consommés annulations règlement')])
summary=[]
for n,(year,q) in enumerate(queries,1):
    path=OUT/f'{n:02d}-{year}.json'
    if path.exists():
        d=json.loads(path.read_text(encoding='utf8'))
        if not d.get('available'):d=None
    else:d=None
    if d is None:
        start=time.monotonic()
        try:
            url='http://127.0.0.1:8552/api/semantic-search?'+urllib.parse.urlencode(dict(q=q,year=year,format='pdf',limit=18))
            with urllib.request.urlopen(url,timeout=120) as r:d=json.load(r)
        except Exception as e:d={'available':False,'error':str(e),'items':[]}
        d['audit_query']={'q':q,'year':year,'mode':'hybrid'}
        d['checked_at']=datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
    row={'number':n,'year':year,'query':q,'available':d.get('available',False),'results':len(d.get('items',[])),'seconds':d.get('elapsed_seconds')}
    summary.append(row)
    (OUT/'progress.json').write_text(json.dumps({'completed':n,'total':len(queries),'queries':summary},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(row,ensure_ascii=False),flush=True)
(OUT/'summary.json').write_text(json.dumps({'complete':True,'automatic_financial_import':False,'queries':summary},ensure_ascii=False,indent=2),encoding='utf8')