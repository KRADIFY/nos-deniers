"""A resumable, independently verified backup. Never modifies the live project."""
import collections
import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent / 'backups/nos-deniers-20260928'
COPY = Path('H:/Sauvegardes-Nos-Deniers/20260928-avant-publication')
SKIP = {'node_modules', '__pycache__', '.git', '.runtime', 'python-libs'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), 'utf-8')
    temp.replace(path)


def walk(folder):
    for parent, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP and not Path(parent, d).is_junction() and not Path(parent, d).is_symlink()]
        for name in files:
            p = Path(parent, name)
            if not p.is_symlink() and not name.endswith(('.pyc', '-wal', '-shm')):
                yield p


def copy_checked(src, dest, expected=None):
    source_hash = expected or sha(src)
    if dest.exists():
        assert dest.stat().st_size == src.stat().st_size and sha(dest) == source_hash, str(dest)
        return source_hash
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.part')
    h = hashlib.sha256()
    before = src.stat()
    with src.open('rb') as incoming, tmp.open('wb') as output:
        for block in iter(lambda: incoming.read(8 * 1024 * 1024), b''):
            h.update(block); output.write(block)
    after = src.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), str(src)
    assert h.hexdigest() == source_hash and sha(tmp) == source_hash, str(dest)
    tmp.replace(dest)
    return source_hash


def core_files():
    selected = set()
    for name in ('budget_service', 'public', 'tests', 'tools', 'assets',
                 'previews/presentation-20260928', 'reports/integration-annexes-20260928',
                 'reports/integration-classeurs-20260928', 'outputs/recherche-manques-suite-20260928',
                 'deploy/update-20260928-annexes'):
        selected.update(walk(ROOT / name))
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix in ('.md', '.yaml', '.txt', '.ps1', '.py', '.cmd'):
            selected.add(p)
    selected.update(ROOT / n for n in ('Dockerfile', 'Dockerfile.retrieval', '.dockerignore', '.gitignore'))
    for p in (ROOT / 'auditeur-independant').iterdir():
        if p.is_file() and p.suffix in ('.py', '.cjs', '.cmd', '.md', '.json'):
            selected.add(p)
    selected.add(ROOT / 'auditeur-independant/Dockerfile')
    selected.update(walk(ROOT / 'auditeur-independant/web'))
    return sorted(selected)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    COPY.mkdir(parents=True, exist_ok=True)
    assert WORK.resolve().is_relative_to(ROOT.parent.resolve())
    assert COPY.resolve().is_relative_to(Path('H:/Sauvegardes-Nos-Deniers').resolve())
    manifest = dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    root=str(ROOT), backup_root=str(COPY), files=[], documents_missing=[],
                    indexes_recomputed=False, production_modified=False)
    # Snapshot code, local data, delta plans and checks in one archive.
    archive = WORK / 'nos-deniers-code-base-et-preuves.zip'
    core_manifest = WORK / 'core-files.json'
    if not archive.exists():
        entries = []
        with zipfile.ZipFile(archive.with_suffix('.zip.part'), 'w', zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
            for p in core_files():
                rel = p.relative_to(ROOT).as_posix()
                if p.name.startswith('.env') or p.suffix in ('.pem', '.key'):
                    raise ValueError('Fichier secret inattendu dans le périmètre')
                fingerprint = sha(p)
                z.write(p, 'budget/' + rel)
                assert sha(p) == fingerprint, 'Fichier modifié pendant la sauvegarde : ' + rel
                entries.append(dict(path='budget/' + rel, bytes=p.stat().st_size, sha256=fingerprint))
        archive.with_suffix('.zip.part').replace(archive)
        dump(core_manifest, entries)
    entries = json.loads(core_manifest.read_text('utf-8'))
    with zipfile.ZipFile(archive) as z:
        assert len(z.infolist()) == len(entries)
        for r in entries:
            with z.open(r['path']) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == r['sha256']
    for p in (archive, core_manifest):
        digest = copy_checked(p, COPY / p.name)
        manifest['files'].append(dict(path=p.name, bytes=p.stat().st_size, sha256=digest, kind='current_snapshot'))
    print(json.dumps(dict(phase='current_snapshot_verified', files=len(entries), bytes=archive.stat().st_size)), flush=True)
    # Frozen original deployment and its three vector indexes. Compressed main
    # indexes already exist: preserve these rather than create vectors again.
    release = ROOT / 'deploy/update-20260924-final'
    transfer = json.loads((release / 'transfer-plan.json').read_text('utf-8'))
    choices = []
    for r in transfer['files']:
        if r['path'] in ('search/search.sqlite', 'search/dense.faiss'):
            p = release / ('search.sqlite.zst' if r['path'].endswith('sqlite') else 'dense.faiss.zst')
            choices.append((p, 'published-20260924/' + p.name, None, dict(expands_to=r['path'], original_bytes=r['bytes'], original_sha256=r['sha256'])))
        else:
            choices.append((Path(r['local']), 'published-20260924/' + r['path'], r['sha256'], {}))
    for p, rel, expected, extra in choices:
        digest = copy_checked(p, COPY / rel, expected)
        manifest['files'].append(dict(path=rel, bytes=p.stat().st_size, sha256=digest, kind='published_restore', **extra))
        dump(COPY / 'manifest.in-progress.json', manifest)
        print(json.dumps(dict(phase='backup_file_verified', path=rel, bytes=p.stat().st_size)), flush=True)
    # Public PDF/workbook corpus: resolve by content hash, never merely by name.
    wanted = json.loads((release / 'all-public-files.json').read_text('utf-8'))
    by_size = collections.defaultdict(list)
    for r in wanted:
        by_size[r['bytes']].append(r)
    candidates = collections.defaultdict(list)
    roots = [ROOT / 'reports/release-20260924-working/data', ROOT / 'vectorisation-nos-deniers-20260909',
             ROOT / 'consolidation-vectorisation-20260924/01_sources_officielles',
             ROOT / 'reports/integration-classeurs-20260928/data', ROOT / 'reports/integration-annexes-20260928/data']
    missing = {r['sha256'] for r in wanted}
    locations = {}
    for base in roots:
        for p in walk(base):
            if p.stat().st_size not in by_size:
                continue
            if not any(r['sha256'] in missing for r in by_size[p.stat().st_size]):
                continue
            h = sha(p)
            if h in missing:
                missing.remove(h); locations[h] = p
    for i, r in enumerate(wanted):
        src = locations.get(r['sha256'])
        if src is None:
            manifest['documents_missing'].append(r)
            continue
        rel = 'published-data/' + r['path']
        copy_checked(src, COPY / rel, r['sha256'])
        manifest['files'].append(dict(path=rel, bytes=r['bytes'], sha256=r['sha256'], kind='public_document'))
        if i % 250 == 0:
            print(json.dumps(dict(phase='public_documents', position=i, expected=len(wanted))), flush=True)
    manifest['complete'] = not manifest['documents_missing']
    manifest['files_count'] = len(manifest['files'])
    manifest['bytes'] = sum(r['bytes'] for r in manifest['files'])
    dump(COPY / 'MANIFEST.json', manifest)
    dump(WORK / 'BACKUP-RECEIPT.json', manifest)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('files', 'documents_missing')}, ensure_ascii=False), flush=True)
    print('DOCUMENTS_MISSING', len(manifest['documents_missing']), flush=True)


if __name__ == '__main__':
    main()
