"""Separate, immutable handoff: leave the corpus under extraction untouched."""
import hashlib,json,shutil,sqlite3
from pathlib import Path
from datetime import datetime,timezone

DATA=Path('/data');OUT=Path('/out')
OUT.mkdir(exist_ok=True);(OUT/'donnees-structurees').mkdir(exist_ok=True);(OUT/'sources').mkdir(exist_ok=True);(OUT/'_controle').mkdir(exist_ok=True)
files=[];metadata={};sources=[]
def register(path,**extra):
    files.append(dict(path=path.relative_to(OUT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,**extra))
for name in ('budget.sqlite','events.sqlite'):
    origin=DATA/'derived'/name;dest=OUT/'donnees-structurees'/name
    assert not dest.exists(), 'Snapshot already exists; preserve it'
    with sqlite3.connect(origin.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(dest) as target:
        source.backup(target)
        assert target.execute('pragma integrity_check').fetchone()[0]=='ok'
        count=source.execute('select count(*) from '+('facts' if name=='budget.sqlite' else 'events')).fetchone()[0]
        metadata[name]={k:json.loads(v) for k,v in source.execute('select * from meta')}
        sources.extend(json.loads(r[0]) for r in source.execute('select data from sources') if json.loads(r[0])['path'].startswith('public/legal/'))
    register(dest,role='validated_structured_data',embed_document=False,records=count)
for source in sources:
    origin=DATA/source['path'];assert hashlib.sha256(origin.read_bytes()).hexdigest()==source['sha256']
    dest=OUT/'sources'/origin.name
    assert not dest.exists();shutil.copyfile(origin,dest)
    register(dest,role='original_api' if source['format']=='json' else 'structured_html',embed_document=source['format']=='html',source_id=source['id'],title=source['title'],url=source['url'],numeric_status='source_table_to_verify_against_validated_sql')
manifest=dict(at=datetime.now(timezone.utc).isoformat(),original_package_unchanged=True,files=files,metadata=metadata,
              canonical_facts=119746,events=186,event_scope='Décret 2024-124 uniquement ; annulations, pas gels',
              policy='Use the newer structured snapshot for calculations. Do not add it to the old 116272-row snapshot; preserve that snapshot as history. Source paths /data are logical: resolve with original inventory plus this manifest.')
(OUT/'_controle/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files),bytes=sum(f['bytes'] for f in files),facts=119746,events=186)))
