from pathlib import Path
p=Path('zeros.py');s=p.read_text('utf-8').replace(r'\b[Nn]',r'(?<![A-Za-z0-9])[Nn]')
p.write_text(s,'utf-8')
import json,collections
d=json.loads(Path('resultats/controle-zeros/zeros-sources.json').read_text('utf-8'))
for reason,count in collections.Counter(i['reason'] for i in d['items'] if i['status']=='undetermined').most_common(15):print(count,reason)
print('Unknown fact formats',collections.Counter(Path(i['source_title']).suffix for i in d['items'] if i['status']=='undetermined' and not i.get('registry')))
