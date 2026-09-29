"""Compare the current public instance with the exact-image staging instance."""
import hashlib
import json
import shlex
import subprocess
from urllib.parse import urlencode

SOURCE = 'marie@109.199.112.132'
TARGET = 'root@5.189.145.254'
PORT = 8552


def fetch(host, path):
    url = f'http://127.0.0.1:{PORT}{path}'
    cmd = f'curl --fail --silent --show-error --max-time 90 {shlex.quote(url)}'
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', host, cmd],
                          capture_output=True, check=True).stdout


def query(path, **parameters):
    return path + '?' + urlencode(parameters)


def difference(a, b, path=''):
    if type(a) is not type(b): return path, type(a).__name__, type(b).__name__
    if isinstance(a, dict):
        if set(a) != set(b): return path+'/keys', sorted(a), sorted(b)
        for key in a:
            diff = difference(a[key], b[key], path+'/'+str(key))
            if diff: return diff
    elif isinstance(a, list):
        if len(a) != len(b): return path+'/length', len(a), len(b)
        for i,(left,right) in enumerate(zip(a,b)):
            diff=difference(left,right,path+'/'+str(i))
            if diff:return diff
    elif a != b:return path,a,b
    return None


def main():
    cases = {
        'assets-js': '/assets/explorer.js',
        'overview': query('/api/explorer',start=2023,end=2025),
        'history-cp': query('/api/explorer',start=2017,end=2022,measure='CP',budget='BG'),
        'history-ae-p176': query('/api/explorer',start=2020,end=2020,measure='AE',budget='BG',scope='SB/176'),
        'cas': query('/api/explorer',start=2022,end=2024,measure='CP',budget='CAS'),
        'inflation': query('/api/explorer',start=2020,end=2022,measure='CP',budget='BG',constant='1',base=2025),
        'exclude': query('/api/explorer',start=2023,end=2025,measure='CP',budget='BG',exclude='["TA/174"]'),
        'p176-proof': query('/api/provenance',start=2020,end=2020,measure='AE',budget='BG',scope='SB/176',year=2020,stage='EXEC',cell_scope='SB/176'),
        'p344-proof': query('/api/provenance',start=2022,end=2022,measure='CP',budget='BG',scope='EB/344',year=2022,stage='OUVERT',cell_scope='EB/344'),
    }
    for label,path in cases.items():
        old,new=fetch(SOURCE,path),fetch(TARGET,path)
        if old!=new:
            if label=='assets-js':raise AssertionError(f'{label}: SHA {hashlib.sha256(old).hexdigest()} != {hashlib.sha256(new).hexdigest()}')
            diff=difference(json.loads(old),json.loads(new))
            raise AssertionError(f'{label}: first difference {diff!r}')
        print(label, 'identical', hashlib.sha256(new).hexdigest(),flush=True)
    print('Exact staging matches the active public service for all sampled numeric responses.',flush=True)

if __name__=='__main__':main()
