"""Restore a public release in an isolated directory using only frozen archives."""
import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/restore-20260910-actions-mpr'
BUNDLE = ROOT / 'deploy/update-20260910-actions-mpr'
CHAIN = [('release-20260908','budget-data.tar.gz'),
         ('update-20260909-ecologie','collection.tar.gz'),
         ('update-20260910-fdc2023','collection.tar.gz')]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_name(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe archive path: '+name)
    return name


def verify_file(root, record):
    p=root/safe_name(record['path'])
    assert p.resolve().is_relative_to(root.resolve()) and not p.is_symlink()
    assert p.is_file() and p.stat().st_size==record['bytes'] and sha(p)==record['sha256'],str(p)


def main():
    assert not OUT.exists(),'Existing restoration must not be overwritten.'
    manifest=read(BUNDLE/'release.json')
    assert manifest['release']=='20260910-actions-mpr'
    assert shutil.disk_usage(ROOT).free > manifest['export']['public_bytes']+1024**3
    OUT.mkdir()
    data=OUT/'data';data.mkdir()
    layers=[]
    for directory,name in CHAIN:
        bundle=ROOT/'deploy'/directory
        release=read(bundle/'release.json')
        records=read(bundle/'data-files.json')
        files=release['files']
        # Original and later manifests all list exact archive and inventory hashes.
        for filename in (name,'data-files.json'):
            record=next(r for r in files if r.get('path',r.get('name'))==filename)
            actual=dict(record,path=filename)
            verify_file(bundle,actual)
        expected={safe_name(r['path']):r for r in records}
        assert len(expected)==len(records)
        print('Restoring',directory,len(records),'files',flush=True)
        with tarfile.open(bundle/name,'r:gz') as archive:
            seen=set()
            for member in archive:
                filename=safe_name(member.name)
                assert member.isfile() and filename in expected and filename not in seen,filename
                seen.add(filename)
                assert member.size==expected[filename]['bytes']
                dest=data/filename
                assert dest.resolve().is_relative_to(data.resolve())
                dest.parent.mkdir(parents=True,exist_ok=True)
                temp=dest.with_name(dest.name+'.restore-part')
                with archive.extractfile(member) as src,temp.open('xb') as dst:
                    shutil.copyfileobj(src,dst)
                assert sha(temp)==expected[filename]['sha256']
                temp.replace(dest)
            assert seen==set(expected)
        layers.append(dict(archive=str(bundle/name),sha256=sha(bundle/name),files=len(records)))
    public=read(BUNDLE/'all-public-files.json')
    expected=public+manifest['reused_data_files']
    print('Verifying all',len(expected),'restored files',flush=True)
    for record in expected:
        verify_file(data,record)
    actual={str(p.relative_to(data)).replace('\\','/') for p in data.rglob('*') if p.is_file()}
    assert actual=={r['path'] for r in expected},'Unexpected or missing restored file'
    for record in manifest['files']:
        verify_file(BUNDLE,record)
    subprocess.run(['docker','image','load','--input',str(BUNDLE/'image.tar')],check=True)
    image='lexmachine-budget:'+manifest['release']
    loaded=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image],text=True).strip()
    assert loaded in (manifest['image_id'],'sha256:'+manifest['image_config_sha256'])
    run=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
         '--security-opt','no-new-privileges','--memory','768m','--cpus','2','--tmpfs','/tmp:size=64m',
         '--mount','type=bind,src='+str(data)+',dst=/data,readonly',
         '--mount','type=bind,src='+str(BUNDLE)+',dst=/bundle,readonly',image]
    print('Checking restored release in an isolated container',flush=True)
    result=subprocess.run(run+['python','/bundle/verify.py'],capture_output=True,text=True,encoding='utf-8')
    (OUT/'offline-verification.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr[-3000:]
    # Database consistency is checked in the restored copy, not the working volume.
    code="""import sqlite3,json
from pathlib import Path
for file,table,count in [('budget.sqlite','facts',120576),('events.sqlite','events',186)]:
 with sqlite3.connect('file:/data/derived/'+file+'?mode=ro',uri=True) as c:
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
  assert c.execute('select count(*) from '+table).fetchone()[0]==count
assert not Path('/data/derived/document-search.sqlite').exists()
print('Numeric and event databases restored; document index not part of this release.')
"""
    subprocess.run(run+['python','-c',code],check=True)
    receipt=dict(passed=True,completed_at=datetime.now(timezone.utc).isoformat(),release=manifest['release'],
                 public_files=len(public),derived_files=len(manifest['reused_data_files']),archives=layers,
                 database_sha256=sha(data/'derived/budget.sqlite'),events_sha256=sha(data/'derived/events.sqlite'),
                 cases=len(manifest['cases']),network='disabled',restored_data='read-only in test container',
                 limitation='No documentary/vector index in this release; its restoration remains to test when delivered.',
                 live_services_modified=False)
    (OUT/'RESTORE-VERIFIED.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
