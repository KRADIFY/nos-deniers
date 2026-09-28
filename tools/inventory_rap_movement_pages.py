"""Inventory national RAP pages containing movement and reserve tables."""
from __future__ import annotations
import argparse,json,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SOURCES=ROOT/'reports/rap-actions-national-20260920/sources.json'
DEFAULT_TEXT=ROOT/'reports/rap-actions-national-20260920/text'
DEFAULT_OUT=ROOT/'reports/rap-movements-national-20260920/inventory.json'

def norm(text):
    return ' '.join(unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().upper().split())

def programme(page):
    patterns=[
        r'Programme\s+n[^\d]{0,3}(\d{3,4})',
        r'PROGRAMME\s+(\d{3,4})',
        r'Programme\s+(\d{3,4})',
    ]
    for pattern in patterns:
        match=re.search(pattern,page,re.I)
        if match:return match.group(1)
    return ''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--sources',type=Path,default=DEFAULT_SOURCES)
    ap.add_argument('--text',type=Path,default=DEFAULT_TEXT);ap.add_argument('--output',type=Path,default=DEFAULT_OUT)
    args=ap.parse_args();sources=json.loads(args.sources.read_text(encoding='utf-8'))
    rows=[];counts=Counter();coverage=defaultdict(lambda:Counter())
    for source in sources:
        cache=args.text/(source['sha256']+'.txt')
        assert cache.exists(),cache
        pages=cache.read_text(encoding='utf-8').split('\f')
        for number,page in enumerate(pages,1):
            normalized=norm(page)
            flags={
                'movement_recap':'RECAPITULATION DES MOUVEMENTS DE CREDITS' in normalized,
                'initial_reserve':'MISE EN RESERVE INITIALE' in normalized,
                'reserve_precaution':'RESERVE DE PRECAUTION' in normalized,
                'end_management':'FIN DE GESTION' in normalized,
                'freezes':'DEGEL' in normalized or 'SURGEL' in normalized or 'CREDITS GELES' in normalized,
            }
            if not any(flags.values()):continue
            row=dict(year=source['year'],mission=source['mission'],program=programme(page),page=number,
                     source=source['source'],sha256=source['sha256'],path=source['path'],flags=flags)
            rows.append(row)
            for key,value in flags.items():
                if value:
                    counts[key]+=1;coverage[(source['year'],source['mission'])][key]+=1
    result={
      'sources_scanned':len(sources),'pages_flagged':len(rows),'counts':dict(counts),
      'mission_years':[
        {'year':year,'mission':mission,**dict(values)}
        for (year,mission),values in sorted(coverage.items())
      ],
      'pages':rows
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('pages','mission_years')}|
                     {'mission_years':len(result['mission_years'])},ensure_ascii=False))

if __name__=='__main__':main()
