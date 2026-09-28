"""Read the nine collected Ecology RAPs, retaining complete page text and locations."""
from pathlib import Path
import hashlib,json,re,subprocess,unicodedata,shutil

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'vectorisation-nos-deniers-20260909'
OUT=ROOT/'reports/reserves-et-consignes-20260909'
OUT.mkdir(parents=True,exist_ok=True)
POPPLER=Path('C:/Users/Jean-Christophe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftotext.exe')
if not POPPLER.exists():POPPLER=Path(shutil.which('pdftotext'))
def fold(t):return ''.join(c for c in unicodedata.normalize('NFKD',t).lower() if not unicodedata.combining(c))
files=[]
for p in (CORPUS/'sources-documentaires').rglob('*.pdf'):
    label=fold(p.name)
    if ('rap-plrg' in p.parts and ('ecologie' in label or 'msn_ta' in label)) or p.name.startswith('RAP2025_BG_Ecologie_'):
        files.append(p)
found=[]
for path in sorted(files):
    year=int(re.search(r'20(?:1[7-9]|2[0-5])',path.name)[0]) if re.search(r'20(?:1[7-9]|2[0-5])',path.name) else int(next(p for p in path.parts if re.fullmatch(r'20\d{2}',p)))
    dest=OUT/f'rap-ecologie-{year}.txt'
    subprocess.run([str(POPPLER),'-layout','-enc','UTF-8',str(path),str(dest)],check=True,capture_output=True)
    pages=dest.read_text(encoding='utf-8').split('\f')
    hits=[]
    for no,text in enumerate(pages,1):
        simple=fold(text)
        terms=[t for t in ['reserve de precaution','mise en reserve initiale','surgel','degel','levee de reserve','credits geles'] if t in simple]
        if not terms:continue
        header=' '.join(text[:450].split())
        hits.append(dict(pdf_page=no,header=header,terms=terms,has_reserve_table='mise en reserve initiale' in simple,text=text))
    result=dict(year=year,path=str(path),export_relative_path=path.relative_to(CORPUS).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=len(pages)-1,found_pages=hits)
    found.append(result)
    print(json.dumps(dict(year=year,pages=result['pages'],matching_pages=len(hits),reserve_tables=[h['pdf_page'] for h in hits if h['has_reserve_table']]),ensure_ascii=False),flush=True)
(OUT/'rap-reserves-pages.json').write_text(json.dumps(found,ensure_ascii=False,indent=2),encoding='utf-8')
