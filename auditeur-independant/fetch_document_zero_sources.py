import json,subprocess,shlex,tarfile
from pathlib import Path
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'));paths=[g['source']['path'] for g in groups]
root=Path('references/physical-sources');root.mkdir(exist_ok=True)
script="""import sys,tarfile,pathlib,json
root=pathlib.Path('/opt/lexmachine-budget/releases/20260924-final/data').resolve()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
 for name in json.loads(sys.stdin.read()):
  p=(root/name).resolve()
  if not p.is_relative_to(root):raise ValueError('unsafe path')
  if p.is_file():tar.add(p,arcname=name,recursive=False)
"""
archive=root/'document-sources.tar'
with archive.open('wb') as f:subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','marie@109.199.112.132','python3 -c '+shlex.quote(script)],input=json.dumps(paths).encode(),stdout=f,check=True)
with tarfile.open(archive) as tar:tar.extractall(root,filter='data')
print(json.dumps(dict(requested=len(paths),bytes=archive.stat().st_size)))
