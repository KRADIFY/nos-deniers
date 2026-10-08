"""Read-only capture of the running Budget application for the private Git backup."""
from pathlib import Path
import gzip,hashlib,io,json,shutil,subprocess,tarfile,urllib.request
stage=Path('/opt/nos-deniers/staging/git-backup-20261008')
stage.mkdir(exist_ok=False)
tree=stage/'tree';tree.mkdir()
def output(*args):return subprocess.check_output(args)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()
def copy_app(container,names,prefix=''):
 raw=output('docker','exec',container,'tar','-C','/app','-cf','-',*names)
 with tarfile.open(fileobj=io.BytesIO(raw)) as t:
  for member in t.getmembers():
   p=Path(member.name)
   assert not p.is_absolute() and '..' not in p.parts
   if not member.isfile() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
   assert p.name not in ('.env','id_rsa') and p.suffix not in ('.pem','.key')
   dest=tree/prefix/p;dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(t.extractfile(member).read())
def copy_file(source,destination):
 dest=tree/destination;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
containers=['nos-deniers-public-web1-1','nos-deniers-public-web2-1','nos-deniers-public-web3-1','nos-deniers-public-web4-1','nos-deniers-public-retrieval-1','nos-deniers-demo-demo-1']
info={name:json.loads(output('docker','inspect',name))[0] for name in containers}
assert len({info[n]['Image'] for n in containers[:4]})==1
copy_app(containers[0],['budget_service','public','tools','tests','requirements.txt'])
copy_app(containers[4],['budget_service'],'runtime-retrieval')
copy_app(containers[5],['public','server.py'],'demo')
copy_file('/opt/nos-deniers/compose.yaml','proofs/compose.yaml')
for name in ['Dockerfile','compose.yaml']:
 copy_file('/opt/nos-deniers-demo/20261005-gateway/'+name,'demo/'+name)
for name in ['general.css','budget-refinements.css','header-alignment.css','header-alignment.js','general-locations.conf']:
 copy_file('/opt/nos-deniers/presentations/'+name,'presentations/'+name)
for name in ['tracker.js','exclusion-bridge.html','exclusion-bridge.js']:
 copy_file('/opt/nos-deniers/presentations/audience-20261006/'+name,'presentations/audience-20261006/'+name)
copy_file('/opt/plfss-demo/releases/20261006-voix/public/entry-buttons.css','presentations/entry-buttons.css')
copy_file('/etc/nginx/sites-enabled/nos-deniers-budget','proofs/nginx-budget.conf')
# Keep the standalone demo source in sync with the stylesheet injected in production.
copy_file('/opt/nos-deniers/presentations/budget-refinements.css','demo/public/budget-refinements.css')
for p in Path('/opt/nos-deniers/releases/20261008-jorf-vectorisation/evidence').iterdir():
 if p.is_file():copy_file(p,'proofs/vectorisation-jorf-20261008/'+p.name)
for i,r in enumerate(['/opt/nos-deniers/releases/20260929-optimisation/search','/opt/nos-deniers/releases/20261002-documents/search-supplement','/opt/nos-deniers/releases/20261008-jorf-vectorisation/search-supplement2']):
 copy_file(Path(r)/'manifest.json','proofs/indices/index-'+str(i)+'-manifest.json')
db=Path('/opt/nos-deniers/releases/20261002-plf2027/data/derived/budget.sqlite')
before=digest(db)
dest=tree/'proofs/budget.sqlite.gz';dest.parent.mkdir(parents=True,exist_ok=True)
with db.open('rb') as source,gzip.open(dest,'wb',compresslevel=6) as target:shutil.copyfileobj(source,target)
assert digest(db)==before
meta=json.load(urllib.request.urlopen('https://budget.lexmachine.net/api/bootstrap',timeout=30))['meta']
files={p.relative_to(tree).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size} for p in tree.rglob('*') if p.is_file()}
assert max(v['bytes'] for v in files.values())<95000000
receipt={'published_url':'https://budget.lexmachine.net/','captured':'2026-10-08','database_sha256':before,'meta':meta,
 'containers':{n:{'image':i['Config']['Image'],'image_id':i['Image'],'mounts':i['Mounts']} for n,i in info.items()},
 'large_vector_indexes_in_git':False,'source_pdf_corpus_in_git':False,'production_modified':False,'files':files}
(tree/'proofs/VERSION-EN-LIGNE.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False))
for n,i in info.items():assert json.loads(output('docker','inspect',n))[0]['Id']==i['Id']
archive=stage/'snapshot.tar.gz'
with tarfile.open(archive,'w:gz') as t:
 for p in tree.rglob('*'):
  if p.is_file():t.add(p,arcname=p.relative_to(tree).as_posix())
print(json.dumps({'archive':str(archive),'sha256':digest(archive),'bytes':archive.stat().st_size,'files':len(files),'database_sha256':before,'production_modified':False}))
