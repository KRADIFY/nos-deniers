import json
from pathlib import Path
import fitz
from oracle import digest
root=Path('references/physical-sources');out=Path('resultats/document-zero-pages');out.mkdir(exist_ok=True)
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'))
for g in groups:
 s=g['source'];p=root/s['path'];assert digest(p)==s['sha256'],s['id']
 if s['format']=='html':continue
 doc=fitz.open(p)
 for page in sorted({r['line'] for r in g['rows']}):
  pag=doc[page-1];(out/f"{s['id']}-{page}.txt").write_text(pag.get_text(sort=True),'utf-8')
  (out/f"{s['id']}-{page}.json").write_text(json.dumps(pag.get_text('words'),ensure_ascii=False),'utf-8')
 print(s['id'],len(g['rows']),'facts',sorted({r['line'] for r in g['rows']}))
print('pages',len(list(out.glob('*.txt'))))
