"""Show compact decoded staged tables for selected PDF pages."""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path


def short(v, limit=500):
    s=json.dumps(v, ensure_ascii=False) if not isinstance(v,str) else v
    s=s.replace('\n',' \\n ')
    return s[:limit]+('…' if len(s)>limit else '')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('path',type=Path); ap.add_argument('pages')
    a=ap.parse_args(); wanted={int(x) for x in a.pages.split(',')}
    with gzip.open(a.path,'rt',encoding='utf-8') as f:
      for n,line in enumerate(f,1):
        r=json.loads(line); page=r.get('page')
        if page not in wanted: continue
        print(f'PAGE {page} record={n} status={r.get("status")} review={r.get("review_required")} tables={len(r.get("tables") or [])}')
        for i,wrapper in enumerate(r.get('tables') or [],1):
          t=wrapper.get('table') or {}
          print(f' TABLE {i} id={t.get("id")} method={t.get("method")} cols={wrapper.get("column_count")} numeric={t.get("numeric_status")} auto={t.get("allow_automatic_numeric_fact")}')
          for k in ('context_before','header','combined_ae_cp_columns','grid','rows','cells'):
            if k in t: print(f'  {k}: {short(t[k],2500 if k in ("grid","rows") else 800)}')
          c=wrapper.get('context') or {}
          print('  preceding_text:',short(c.get('preceding_text',''),1000))

if __name__=='__main__': main()