#!/usr/bin/env python3
"""Install the frozen corrected release; retain prior data, images and index mounts."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time

NAME = '20260924-final'
ROOT = Path('/opt/lexmachine-budget')
NEW = ROOT / 'releases' / NAME
INCOMING = Path(__file__).resolve().parent
PROJECT = 'lexmachine-budget-public'
CORE = {'image.tar', 'retrieval-image.tar.gz', 'collection.tar.gz', 'data-files.json',
        'all-public-files.json', 'audit-certificate.json', 'image-code-manifest.json',
        'compose.yaml', 'verify.py', 'update.py'}
REPLACEABLE = {'derived/budget.sqlite', 'derived/events.sqlite',
               'derived/normalization-report.json', 'derived/data-audit.json'}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.json-part')
    if temporary.exists() or temporary.is_symlink():
        raise ValueError('Unexpected temporary file: ' + str(temporary))
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.chmod(0o644)
    temporary.replace(path)


def valid_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or name != path.as_posix():
        raise ValueError('Unsafe relative path: ' + name)
    return name


def check_files(root, records):
    root = Path(root).resolve()
    seen = set()
    for item in records:
        name = valid_name(item['path'])
        path = root / name
        if name in seen or path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Unexpected file: ' + name)
        seen.add(name)
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('File hash/size mismatch: ' + name)


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def output(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True)


def safe_root(path):
    path = Path(path)
    if path.is_symlink() or (path.exists() and path.stat().st_uid != 0):
        raise ValueError('Expected root-owned non-symlink path: ' + str(path))


def permissions(root, records):
    """The non-root verifier must read release.json too; it is not self-listed."""
    root = Path(root)
    folders = {root}
    paths = {root / valid_name(item['path']) for item in records}
    paths.update({root / 'release.json', root / 'READY.json'})
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unexpected permission target: ' + str(path))
        parent = path.parent
        while parent != root:
            folders.add(parent)
            parent = parent.parent
    for folder in sorted(folders, key=lambda value: len(value.parts)):
        folder.chmod(0o755)
    for path in paths:
        path.chmod(0o644)


def validate_manifest(release):
    if release.get('schema_version') != 2 or release.get('release') != NAME:
        raise ValueError('Unexpected release/schema')
    old = Path(release['previous_release'])
    if old.parent != ROOT / 'releases' or old == NEW or old.name in ('', '.', '..'):
        raise ValueError('Unexpected predecessor')
    if old.name != '20260910-reactivation':
        raise ValueError('This complete release must start from public20260910-reactivation')
    index_files = set()
    for key, prefix in [('retrieval_index', 'search'), ('retrieval_supplement', 'search-supplement'), ('retrieval_incremental', 'search-supplement2')]:
        manifest = release[key]
        if manifest.get('state') != 'ready':
            raise ValueError('Index not ready: ' + prefix)
        index_files.add(prefix + '/manifest.json')
        index_files.update(prefix + '/' + valid_name(item['path']) for item in manifest['files'])
    if {item['path'] for item in release['files']} != CORE | index_files:
        raise ValueError('Unexpected delivery file inventory')
    base = release['retrieval_index']
    for name in ('retrieval_supplement', 'retrieval_incremental'):
        extra = release[name]
        if extra['base_input_sha256'] != base['input_sha256']:
            raise ValueError(name + '/base generation mismatch')
        for field in ('model', 'revision', 'dimension', 'version'):
            if base[field] != extra[field]:
                raise ValueError(name + '/base model mismatch')
    if set(release['counts']) != {'facts', 'sources', 'sql_sources', 'events'} or any(type(value) is not int or value < 1 for value in release['counts'].values()):
        raise ValueError('Missing reviewed counts')
    installation = release.get('installation', {})
    if set(installation) != {'minimum_free_bytes', 'minimum_available_memory_bytes'} or any(type(value) is not int or value < 1 for value in installation.values()):
        raise ValueError('Missing reviewed installation resource requirements')
    for role in ('web', 'retrieval'):
        if not release['images'][role]['id'].startswith('sha256:') or len(release['images'][role]['config_sha256']) != 64:
            raise ValueError('Missing reviewed image identity')
    return old


def resume_snapshot(source, destination):
    """Resume only missing inherited links, preserving already replaced delta bytes."""
    source, destination = Path(source).resolve(), Path(destination)
    if destination.is_symlink():
        raise ValueError('Snapshot destination is a symlink')
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    destination = destination.resolve()
    for path in sorted(source.rglob('*'), key=lambda item: (len(item.parts), str(item))):
        target = destination / path.relative_to(source)
        if path.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(destination):
            raise ValueError('Symlink or escaped snapshot path')
        if path.is_dir():
            target.mkdir(mode=0o755, exist_ok=True)
        elif path.is_file():
            if target.exists():
                if not target.is_file(): raise ValueError('Unexpected snapshot file type')
            else:
                os.link(path, target)
        else:
            raise ValueError('Unexpected predecessor entry type')


def extract_delta(archive_path, destination, records):
    destination = Path(destination).resolve()
    expected = {valid_name(item['path']): item for item in records}
    if len(expected) != len(records):
        raise ValueError('Duplicate data path')
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {item.name for item in members} != set(expected):
            raise ValueError('Unexpected collection inventory')
        for member in members:
            name = valid_name(member.name)
            path = destination / name
            item = expected[name]
            if not member.isfile() or path.is_symlink() or not path.resolve().is_relative_to(destination) or member.size != item['bytes']:
                raise ValueError('Invalid archive entry: ' + name)
            if path.exists() and digest(path) == item['sha256']:
                continue
            if path.exists() and name not in REPLACEABLE:
                raise ValueError('A different original source occupies path: ' + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + '.corrections-part')
            if temp.exists() or temp.is_symlink():
                raise ValueError('Unexpected extraction temporary file')
            with archive.extractfile(member) as source, temp.open('xb') as target:
                shutil.copyfileobj(source, target)
            temp.chmod(0o644)
            if digest(temp) != item['sha256']:
                raise ValueError('Extracted bytes differ: ' + name)
            temp.replace(path)  # break a hardlink; the predecessor is never rewritten
    check_files(destination, records)


def index_install(release, source_root, target_root):
    for item in release['files']:
        if not item['path'].startswith(('search/', 'search-supplement/', 'search-supplement2/')):
            continue
        source, target = Path(source_root) / item['path'], Path(target_root) / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o755)
        if target.is_symlink():
            raise ValueError('Index target is a symlink')
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                if shutil.disk_usage(target.parent).free < source.stat().st_size + release['installation']['minimum_free_bytes']:
                    raise ValueError('Insufficient space for index copy between volumes')
                temporary = target.with_name(target.name + '.index-part')
                with source.open('rb') as src, temporary.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                temporary.chmod(0o644)
                if digest(temporary) != item['sha256']:
                    raise ValueError('Copied index differs')
                temporary.replace(target)
        target.chmod(0o644)
        check_files(target_root, [item])


def rollback_commands(old, new, previous_services):
    if 'web' not in previous_services:
        raise ValueError('Previous web service absent')
    services = ['retrieval', 'web'] if 'retrieval' in previous_services else ['web']
    commands = [['docker', 'compose', '-f', str(Path(old) / 'compose.yaml'), 'up', '-d', '--no-deps'] + services]
    if 'retrieval' not in previous_services:
        commands.append(['docker', 'compose', '-f', str(Path(new) / 'compose.yaml'), 'stop', 'retrieval'])
    return commands


def apply_rollback(record):
    old, new = Path(record['previous_release']), Path(record['new_release'])
    if old.parent != ROOT / 'releases' or new != NEW:
        raise ValueError('Unexpected rollback targets')
    for path in (old, new, old / 'compose.yaml', old / 'data/derived/budget.sqlite'):
        safe_root(path)
    if digest(old / 'compose.yaml') != record['previous_compose_sha256'] or digest(old / 'data/derived/budget.sqlite') != record['previous_database_sha256']:
        raise ValueError('Predecessor changed; automatic rollback refused')
    running = active_web(required=False)
    candidates = [running] if running is not None else web_containers(all_states=True)
    for container in candidates:
        working = container['Config']['Labels'].get('com.docker.compose.project.working_dir')
        if working not in (str(old), str(new)):
            raise ValueError('Another release owns the web container; rollback must not replace it')
    for command in rollback_commands(old, new, record['previous_services']):
        run(*command)
    prior = new / 'previous-deployment.json'
    if prior.exists():
        if digest(prior) != record['previous_deployment_sha256']:
            raise ValueError('Previous deployment metadata changed')
        temporary = ROOT / 'deployment.json.rollback-part'
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('Unexpected rollback metadata target')
        shutil.copyfile(prior, temporary)
        temporary.chmod(0o644)
        temporary.replace(ROOT / 'deployment.json')
    print('Previous web/retrieval images and index mounts restored through its preserved compose.', flush=True)


def web_containers(all_states=False):
    args = ['docker', 'ps', '-q']
    if all_states: args.append('-a')
    args.extend(['--filter', 'label=com.docker.compose.project=' + PROJECT,
                 '--filter', 'label=com.docker.compose.service=web'])
    ids = output(*args).split()
    return json.loads(output('docker', 'inspect', *ids)) if ids else []


def active_web(required=True):
    containers = web_containers()
    if not containers and not required:
        return None
    if len(containers) != 1:
        raise ValueError('Unexpected active Budget web service')
    return containers[0]


def verify_compose(config, release, destination):
    if config.get('name') != PROJECT or set(config.get('services', {})) != {'web', 'retrieval'}:
        raise ValueError('Unexpected compose project/services')
    expected = {'web': {'/data': str(destination / 'data')},
                'retrieval': {'/search': str(destination / 'search'), '/search-supplement': str(destination / 'search-supplement'), '/search-supplement2': str(destination / 'search-supplement2')}}
    for role, targets in expected.items():
        service = config['services'][role]
        if service.get('image') != release['images'][role]['tag'] or str(service.get('user')) != '10001:10001' or not service.get('read_only'):
            raise ValueError('Unexpected service image/user/read-only setting')
        mounts = service.get('volumes', [])
        if len(mounts) != len(targets):
            raise ValueError('Unexpected service mount count')
        for mount in mounts:
            if mount.get('type') != 'bind' or mount.get('target') not in targets or mount.get('source') != targets[mount['target']] or not mount.get('read_only'):
                raise ValueError('Unexpected or writable service mount')
    web = config['services']['web']
    retrieval = config['services']['retrieval']
    if web.get('environment', {}).get('BUDGET_RETRIEVAL_URL') != 'http://retrieval:8090' or retrieval.get('ports'):
        raise ValueError('Unexpected retrieval routing/exposure')
    env = retrieval.get('environment', {})
    if (env.get('BUDGET_RETRIEVAL_ROOT') != '/search' or env.get('BUDGET_RETRIEVAL_SUPPLEMENT_ROOT') != '/search-supplement'
            or env.get('BUDGET_RETRIEVAL_SUPPLEMENT2_ROOT') != '/search-supplement2'):
        raise ValueError('All three index mounts must be configured')


def check_installation_storage(minimum_free_bytes):
    """Check the release and Docker filesystems before staging/loading images."""
    release_root = ROOT.resolve(strict=True)
    if shutil.disk_usage(release_root).free < minimum_free_bytes:
        raise ValueError('Insufficient free space for reviewed installation budget')
    raw = json.loads(output('docker', 'info', '--format', '{{json .DockerRootDir}}'))
    if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        raise ValueError('DockerRootDir must be an absolute local directory')
    try:
        docker_root = Path(raw).resolve(strict=True)
    except OSError as exc:
        raise ValueError('DockerRootDir is not accessible on this host') from exc
    if not docker_root.is_dir():
        raise ValueError('DockerRootDir is not a local directory')
    distinct = docker_root.stat().st_dev != release_root.stat().st_dev
    if distinct and shutil.disk_usage(docker_root).free < minimum_free_bytes:
        raise ValueError('Insufficient free space in the DockerRootDir filesystem for the reviewed installation budget')
    return dict(release_root=str(release_root), docker_root=str(docker_root),
                distinct_filesystems=distinct, minimum_free_bytes=minimum_free_bytes)


def activate():
    release = read(INCOMING / 'release.json')
    old = validate_manifest(release)
    ready = read(INCOMING / 'READY.json')
    release_sha = digest(INCOMING / 'release.json')
    if ready.get('state') != 'prepared_and_locally_verified' or ready.get('release_sha256') != release_sha:
        raise ValueError('Release not frozen and locally verified')
    for path in (ROOT, ROOT / 'releases', old, old / 'data', NEW):
        safe_root(path)
    print('Verifying transferred files and both indexesâ€¦', flush=True)
    check_files(INCOMING, release['files'])
    permissions(INCOMING, release['files'])
    for key, directory in [('retrieval_index', 'search'), ('retrieval_supplement', 'search-supplement'), ('retrieval_incremental', 'search-supplement2')]:
        if read(INCOMING / directory / 'manifest.json') != release[key]:
            raise ValueError('Index manifest differs from release contract')
    if digest(old / 'data/derived/budget.sqlite') != release['previous_database_sha256']:
        raise ValueError('Predecessor database differs; no service changed')
    info = active_web()
    working = info['Config']['Labels'].get('com.docker.compose.project.working_dir')
    if working == str(NEW):
        if not (NEW / 'release.json').is_file() or digest(NEW / 'release.json') != release_sha:
            raise ValueError('Another release is already active at the target path')
        run(sys.executable, INCOMING / 'verify.py', '--http', 'http://127.0.0.1:8552')
        print('This exact release is already active; no service changed.', flush=True)
        return
    if working != str(old):
        raise ValueError('Active release differs from reviewed predecessor: ' + str(working))
    if info['Image'] not in release['previous_images']['web']:
        raise ValueError('Active predecessor image differs from reviewed image')
    required = release['installation']
    check_installation_storage(required['minimum_free_bytes'])
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    if available < required['minimum_available_memory_bytes']:
        raise ValueError('Insufficient available memory')
    for item in (old / 'data').rglob('*'):
        if item.is_symlink(): raise ValueError('Symlink in predecessor data')
    marker = NEW / 'STAGING.json'
    if not NEW.exists():
        NEW.mkdir(mode=0o755)
        dump(marker, dict(release_sha256=release_sha))
    elif (marker.is_file() and not marker.is_symlink()
          and read(marker).get('release_sha256') == 'c3218b9ef2133530687ad7441d9e8fcc0f782b29f43e6a36690bbaa7f0a68279'
          and not (NEW / 'release.json').exists()):
        # Resume only the exact failed staging attempt after its inventory correction.
        # The predecessor, active service and incoming payload were verified above.
        dump(marker, dict(release_sha256=release_sha,
                          resumed_inventory_correction=True))
    elif not marker.is_file() or read(marker).get('release_sha256') != release_sha:
        raise ValueError('Existing destination was not prepared for this release')
    destination = NEW / 'data'
    resume_snapshot(old / 'data', destination)
    safe_root(destination)
    for item in destination.rglob('*'):
        if item.is_symlink(): raise ValueError('Symlink in staged data')
    records = read(INCOMING / 'data-files.json')
    extract_delta(INCOMING / 'collection.tar.gz', destination, records)
    all_files = read(INCOMING / 'all-public-files.json')
    if len(all_files) != release['export']['public_files']:
        raise ValueError('Public inventory count mismatch')
    check_files(destination, all_files)
    for name, table, key in [('budget.sqlite', 'facts', 'facts'), ('events.sqlite', 'events', 'events')]:
        with closing(sqlite3.connect((destination / 'derived' / name).as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('SELECT count(*) FROM ' + table).fetchone()[0] != release['counts'][key]:
                raise ValueError('Database integrity/count differs: ' + name)
    index_install(release, INCOMING, NEW)
    previous_config = json.loads(output('docker', 'compose', '-f', old / 'compose.yaml', 'config', '--format', 'json'))
    for role in ('web', 'retrieval'):
        prior = previous_config.get('services', {}).get(role)
        if prior and prior.get('image') == release['images'][role]['tag']:
            raise ValueError('New image tag would overwrite a predecessor rollback tag')
    for role, archive in [('web', 'image.tar'), ('retrieval', 'retrieval-image.tar.gz')]:
        run('docker', 'image', 'load', '--input', INCOMING / archive)
        image = release['images'][role]
        actual = output('docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']).strip()
        if actual not in (image['id'], 'sha256:' + image['config_sha256']):
            raise ValueError('Loaded image differs: ' + role)
    test = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--user', '10001:10001',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--memory', '1024m', '--cpus', '2',
            '--tmpfs', '/tmp:size=128m,mode=1777', '--mount', 'type=bind,source=' + str(destination) + ',target=/data,readonly',
            '--mount', 'type=bind,source=' + str(INCOMING) + ',target=/bundle,readonly', release['images']['web']['tag']]
    print('Checking frozen data, code and contract as UID 10001, without networkâ€¦', flush=True)
    run(*test, 'python', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    run(*test, 'python', '/bundle/verify.py')
    for name in ('compose.yaml', 'update.py', 'verify.py', 'release.json'):
        target = NEW / name
        if target.is_symlink(): raise ValueError('Unexpected release target symlink')
        shutil.copyfile(INCOMING / name, target)
        target.chmod(0o644)
        if digest(target) != digest(INCOMING / name): raise ValueError('Release file changed while copying')
    compose_config = json.loads(output('docker', 'compose', '-f', NEW / 'compose.yaml', 'config', '--format', 'json'))
    verify_compose(compose_config, release, NEW)
    services = output('docker', 'compose', '-f', old / 'compose.yaml', 'config', '--services').split()
    if 'web' not in services: raise ValueError('Previous compose has no web service')
    backup = dict(previous_release=str(old), new_release=str(NEW), previous_services=services,
                  previous_database_sha256=release['previous_database_sha256'], previous_compose_sha256=digest(old / 'compose.yaml'),
                  old_web_container=info['Id'], old_web_image=info['Image'],
                  rollback_command='sudo python3 ' + str(NEW / 'update.py') + ' --rollback')
    deployment = ROOT / 'deployment.json'
    if deployment.exists():
        safe_root(deployment)
        shutil.copyfile(deployment, NEW / 'previous-deployment.json')
        backup['previous_deployment_sha256'] = digest(NEW / 'previous-deployment.json')
    dump(NEW / 'rollback.json', backup)
    print('Prior release retained; activating only Budget web and retrievalâ€¦', flush=True)
    try:
        run('docker', 'compose', '-f', NEW / 'compose.yaml', 'up', '-d', '--no-deps', 'retrieval', 'web')
        for attempt in range(18):
            check = subprocess.run([sys.executable, str(INCOMING / 'verify.py'), '--http', 'http://127.0.0.1:8552'], capture_output=True, text=True)
            if check.returncode == 0:
                print(check.stdout, flush=True)
                break
            time.sleep(5)
        else:
            raise ValueError('Local HTTP release validation failed: ' + check.stderr[-2000:])
        run(sys.executable, INCOMING / 'verify.py', '--http', 'https://' + release['domain'])
        if digest(old / 'data/derived/budget.sqlite') != release['previous_database_sha256']:
            raise ValueError('Predecessor database changed after installation')
    except BaseException:
        print('Verification failed; restoring prior services and index mounts.', flush=True)
        apply_rollback(backup)
        raise
    dump(ROOT / 'deployment.json', dict(domain=release['domain'], release=str(NEW), previous=str(old), state='published',
         fact_count=release['counts']['facts'], source_count=release['counts']['sources'], data_version=release['data_version'],
         rollback=str(NEW / 'rollback.json'), release_sha256=release_sha))
    print('Release verified: https://' + release['domain'] + '/', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if getattr(os, 'geteuid', lambda: -1)() != 0:
        raise ValueError('Run with sudo python3; no service changed')
    if socket.gethostname() != 'vmi3274092':
        raise ValueError('Unexpected host; no service changed')
    import fcntl
    safe_root(ROOT)
    lockpath = ROOT / '.update.lock'
    safe_root(lockpath)
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            safe_root(NEW)
            apply_rollback(read(NEW / 'rollback.json'))
        else:
            activate()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Installation interrupted: ' + str(error), file=sys.stderr)
        sys.exit(1)
