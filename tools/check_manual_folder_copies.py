"""Read-only SHA-256 comparison before a user removes their collection folder."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,datetime

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/Jean-Christophe/Desktop/Nouveau dossier')
CORPUS=ROOT/'vectorisation-nos-deniers-20260909'
OUT=ROOT/'reports/reserves-et-consignes-20260909'
assert SOURCE.is_dir() and CORPUS.is_dir()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

originals=[]
for path in sorted(SOURCE.rglob('*')):
 if path.is_file():
  stat=path.stat();originals.append(dict(path=str(path),relative_path=path.relative_to(SOURCE).as_posix(),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=sha(path)))
sizes={r['bytes'] for r in originals}
candidates=defaultdict(list)
for path in CORPUS.rglob('*'):
 if path.is_file() and path.stat().st_size in sizes:candidates[path.stat().st_size].append(path)
cache={};rows=[]
for original in originals:
 matches=[]
 for path in candidates[original['bytes']]:
  if path not in cache:cache[path]=sha(path)
  if cache[path]==original['sha256']:matches.append(str(path))
 rows.append(dict(**original,copies=matches,status='identical_copy_verified' if matches else 'no_identical_copy_found'))
assert sorted(str(p) for p in SOURCE.rglob('*') if p.is_file())==sorted(r['path'] for r in originals),'Source directory changed while checking'
for original in originals:
 stat=Path(original['path']).stat()
 assert (stat.st_size,stat.st_mtime_ns)==(original['bytes'],original['mtime_ns']),'Source file changed while checking'
summary=dict(checked_at=datetime.datetime.now().astimezone().isoformat(),source=str(SOURCE),archive_root=str(CORPUS),files=len(rows),unique_sha256=len({r['sha256'] for r in rows}),total_bytes=sum(r['bytes'] for r in rows),verified=sum(bool(r['copies']) for r in rows),missing=[r['relative_path'] for r in rows if not r['copies']],all_source_files_have_identical_archived_copy=bool(rows) and all(r['copies'] for r in rows),deleted=False)
OUT.mkdir(exist_ok=True)
(OUT/'controle-nouveau-dossier.json').write_text(json.dumps(dict(summary=summary,files=rows),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
