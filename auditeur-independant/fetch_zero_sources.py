"""Copy only CSV/XLS inputs of zero-valued facts from the user's existing VPS."""
import subprocess,sqlite3,json,tarfile,shlex
from pathlib import Path
db=sqlite3.connect('references/20260924-final/budget.sqlite')
ids={r[0] for r in db.execute('select distinct source from facts where cents=0')}
sources={sid:json.loads(data) for sid,data in db.execute('select id,data from sources')}
paths=[s['path'] for sid,s in sources.items() if sid in ids and s.get('format') in ('csv','xls')]
root=Path('references/physical-sources');root.mkdir(exist_ok=True)
script="""import sys,tarfile,pathlib,json
root=pathlib.Path('/opt/lexmachine-budget/releases/20260924-final/data').resolve()
paths=json.loads(sys.stdin.read())
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
 for name in paths:
  p=(root/name).resolve()
  if not p.is_relative_to(root):raise ValueError('unsafe path')
  if p.is_file():tar.add(p,arcname=name,recursive=False)
"""
archive=root/'sources.tar'
with archive.open('wb') as f:subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','marie@109.199.112.132','python3 -c '+shlex.quote(script)],input=json.dumps(paths).encode(),stdout=f,check=True)
with tarfile.open(archive) as tar:tar.extractall(root,filter='data')
print(json.dumps(dict(requested=len(paths),bytes=archive.stat().st_size,root=str(root.resolve()))))
