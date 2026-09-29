#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 && $(hostname) == vmi3304602 ]] || {
  echo 'Hôte ou utilisateur inattendu : arrêt sans changement.' >&2
  exit 1
}

stage=/opt/nos-deniers/staging/20260929
release=/opt/nos-deniers/releases/20260929-optimisation
test -f "$stage/data.tar"
test -f "$stage/retrieval-image.tar.gz"
test -f "$stage/compose.yaml"

python3 - "$stage" <<'PYCODE'
import hashlib, json, sys, tarfile
from pathlib import Path, PurePosixPath

root=Path(sys.argv[1])
release=Path('/opt/nos-deniers/releases/20260929-optimisation')
def located(name):
    path=root/name
    return path if path.exists() else release/name
checks={
    'data.tar': ('920a5c38b0205d487e5fdec2d96517317ef9a9fee00a84e373cf420d9a3eb05d',4738887680),
    'retrieval-image.tar.gz': ('685be272bbb42fe4a9e617e7cb8ffffc438b97601046c6ac4560433586018a53',3381399255),
    'search/manifest.json': ('d8389e7ed25737ad03480724a21a9decece2c3eeebc9a3058d29f0a190c0f076',802),
    'search-supplement/manifest.json': ('205fc398e9a343eb29adee7c9bbfd738403a52ed0e42e5ebf5dd5fe51857f60a',15523),
    'search-supplement2/manifest.json': ('6b16ba666d81ec6e70597d3ad8570fdb9dde9b9694417eb1ec4020a809bb7b08',887),
}
for directory in ('search','search-supplement','search-supplement2'):
    manifest=json.loads(located(f'{directory}/manifest.json').read_text())
    if manifest.get('state')!='ready' or manifest.get('model')!='BAAI/bge-m3':
        raise SystemExit(f'Manifeste invalide : {directory}')
    for item in manifest['files']:
        checks[f"{directory}/{item['path']}"]=(item['sha256'],item['bytes'])
for name,(expected,size) in checks.items():
    path=located(name)
    if path.stat().st_size!=size: raise SystemExit(f'Taille invalide : {name}')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024),b''):
            digest.update(chunk)
    if digest.hexdigest()!=expected: raise SystemExit(f'Empreinte invalide : {name}')
    print(f'Vérifié : {name}',flush=True)
count=0
with tarfile.open(root/'data.tar','r:') as archive:
    for item in archive:
        path=PurePosixPath(item.name)
        if path.is_absolute() or '..' in path.parts or path.parts[0]!='data' or not (item.isfile() or item.isdir()):
            raise SystemExit(f'Entrée inattendue dans l’archive : {item.name}')
        count+=item.isfile()
if count!=4309: raise SystemExit(f'Nombre de fichiers inattendu : {count}')
print(f'Archive sûre : {count} fichiers',flush=True)
PYCODE

install -d -m 755 "$release" "$release/unpacked"
if [[ ! -d "$release/data" ]]; then
  tar --no-same-owner -xf "$stage/data.tar" -C "$release/unpacked"
  python3 - "$release/unpacked/data" <<'PYCODE'
import sqlite3,sys
from pathlib import Path
data=Path(sys.argv[1])
if sum(1 for x in data.rglob('*') if x.is_file())!=4309: raise SystemExit('Extraction incomplète')
db=sqlite3.connect(f'file:{data/"derived/budget.sqlite"}?mode=ro&immutable=1',uri=True)
if db.execute('pragma quick_check').fetchone()[0]!='ok': raise SystemExit('SQLite invalide')
facts=db.execute('select count(*) from facts').fetchone()[0]
if facts!=135187: raise SystemExit(f'Nombre de faits inattendu : {facts}')
print(f'Base vérifiée : {facts} faits',flush=True)
PYCODE
  mv "$release/unpacked/data" "$release/data"
fi
python3 - "$release/data" <<'PYCODE'
import sqlite3,sys
from pathlib import Path
data=Path(sys.argv[1])
if sum(1 for x in data.rglob('*') if x.is_file())!=4309: raise SystemExit('Delivered data incomplete')
db_path=data/'derived/budget.sqlite'
db=sqlite3.connect(f'file:{db_path}?mode=ro&immutable=1',uri=True)
if db.execute('pragma quick_check').fetchone()[0]!='ok': raise SystemExit('Delivered SQLite invalid')
if db.execute('select count(*) from facts').fetchone()[0]!=135187: raise SystemExit('Delivered facts unexpected')
PYCODE

for name in search search-supplement search-supplement2; do
  if [[ ! -d "$release/$name" ]]; then mv "$stage/$name" "$release/$name"; fi
done
install -o root -g root -m 0644 "$stage/compose.yaml" /opt/nos-deniers/compose.yaml

if ! docker image inspect lexmachine-budget-retrieval:20260924-final >/dev/null 2>&1; then
  gzip -dc "$stage/retrieval-image.tar.gz" | docker load
fi
docker image inspect lexmachine-budget-retrieval:20260924-final >/dev/null
docker image inspect lexmachine-budget:20260929-consultation-chaude >/dev/null
docker compose -f /opt/nos-deniers/compose.yaml config -q
docker compose -f /opt/nos-deniers/compose.yaml up -d --wait --wait-timeout 240

for port in 8552 8556 8557 8558; do
  curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${port}/readyz" >/dev/null
done
echo 'Nos Deniers prêt sur quatre serveurs web locaux ; aucun DNS modifié.'
