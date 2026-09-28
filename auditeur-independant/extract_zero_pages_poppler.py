import json,subprocess,shutil,xml.etree.ElementTree as ET
from pathlib import Path
from oracle import digest
runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
root=Path('references/physical-sources');out=Path('resultats/document-zero-pages');out.mkdir(exist_ok=True)
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'))
for g in groups:
 s=g['source'];p=root/s['path'];assert digest(p)==s['sha256'],s['id']
 if s['format']=='html':continue
 for page in sorted({r['line'] for r in g['rows']}):
  stem=out/f"{s['id']}-{page}"
  for mode,suffix in [('-layout','.txt'),('-bbox-layout','.xml')]:
   subprocess.run([shutil.which('pdftotext'),'-f',str(page),'-l',str(page),mode,str(p),str(stem)+suffix],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
  doc=ET.parse(str(stem)+'.xml');words=[dict(text=w.text,**{k:float(v) for k,v in w.attrib.items()}) for w in doc.iter() if w.tag.endswith('}word')]
  (Path(str(stem)+'.json')).write_text(json.dumps(words,ensure_ascii=False),'utf-8')
print('pages',len(list(out.glob('*.txt'))))
