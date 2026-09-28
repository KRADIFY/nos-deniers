"""One-time targeted integration of the 163 reviewed documentary facts."""
from pathlib import Path
import json

p=Path('zeros.py');s=p.read_text('utf-8')
s=s.replace('from oracle import digest,nodepath','from oracle import digest,nodepath\nfrom document_zeros import DocumentProofs')
s=s.replace("def __init__(self,root):self.root=Path(root).resolve() if root else None;self.cache={}","def __init__(self,root):\n        self.root=Path(root).resolve() if root else None;self.cache={};self.documents=DocumentProofs()")
s=s.replace("else:result={'document_only':True}","else:result={'document_only':True,'path':p}")
s=s.replace("if data.get('document_only'):\n            note=", "if data.get('document_only'):\n            reviewed=self.documents.inspect(f,s,data['path'])\n            if reviewed is not None:return reviewed\n            note=")
p.write_text(s,'utf-8')
p=Path('web/zeros.js');s=p.read_text('utf-8');s=s.replace("if(item.location)raw.append", "if(item.location?.kind==='pdf')raw.append(text('small','PDF · page '+item.location.page+' · repères contrôlés dans le document'));\n  else if(item.location?.kind==='html')raw.append(text('small','Tableau '+item.location.table+' · ligne '+item.location.row+' · colonne '+item.location.columns.join(', ')));\n  else if(item.location)raw.append")
p.write_text(s,'utf-8')
p=Path('Dockerfile');s=p.read_text('utf-8').replace('chromium ca-certificates tzdata','chromium ca-certificates tzdata poppler-utils').replace('zeros.py prepare_reference.py','zeros.py document_zeros.py document-zero-proofs.json prepare_reference.py');p.write_text(s,'utf-8')
p=Path('.dockerignore');s=p.read_text('utf-8')+'\n!document_zeros.py\n!document-zero-proofs.json\n';p.write_text(s,'utf-8')
p=Path('build_delivery.py');s=p.read_text('utf-8').replace("'zeros.py','prepare_reference.py'","'zeros.py','document_zeros.py','document-zero-proofs.json','prepare_reference.py'").replace("'test_zero_api.py']","'test_zero_api.py','test_document_zeros.py']").replace('local_unit_tests=30','local_unit_tests=35');p.write_text(s,'utf-8')
p=Path('install.py');s=p.read_text('utf-8').replace("'test_zero_api'","'test_zero_api','test_document_zeros'");p.write_text(s,'utf-8')
p=Path('audit.py');s=p.read_text('utf-8').replace("'management.py','zeros.py'","'management.py','zeros.py','document_zeros.py','document-zero-proofs.json'");p.write_text(s,'utf-8')
# Keep the scope printed in the 2019 schedules visible. The zero cell is
# confirmed, while the auditor must not call the HORS T2 schedule all-titles.
p=Path('document-zero-proofs.json');d=json.loads(p.read_text('utf-8'))
for proof in d['proofs']:
    if proof['fact']['year']==2019 and 'E1' in ' '.join(x.get('text','') for x in proof.get('fragments',[])) or (proof['fact']['year']==2019 and 'P1' in ' '.join(x.get('text','') for x in proof.get('fragments',[]))):
        proof['reason']=proof['reason'].replace(' ; programme sans dépenses de personnel dans le RAP contrôlé.','. Ce repère confirme la valeur nulle ; la mention hors titre 2 reste attachée à la preuve et ne vaut pas règle générale pour les autres programmes.')
p.write_text(json.dumps(d,ensure_ascii=False,indent=2),'utf-8')
print('Integrated documentary proof replay')
