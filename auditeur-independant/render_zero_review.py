import json,subprocess,shutil
from pathlib import Path
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'))
catalog={g['source']['id']:g['source'] for g in groups};root=Path('references/physical-sources');out=Path('resultats/document-zero-pages')
for sid,page in [('9099e2f12825d8806e5c',155),('5e4f9c2d55d0a31e3fe6',103),('2c7bd4ed0a8aaeaba95c',9),('f25726d1f9880dc19258',9),('56a7f6c13572e199a706',50),('5a7f13b14297211eb877',6)]:
    subprocess.run([shutil.which('pdftoppm'),'-f',str(page),'-l',str(page),'-scale-to','1300','-singlefile','-png',str(root/catalog[sid]['path']),str(out/f'{sid}-{page}')],capture_output=True,check=True)
print('Six pages rendered')
