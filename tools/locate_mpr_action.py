"""Attach the four reviewed MPR execution amounts to RAP action 02."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'budget_service/data/maprimerenov.json'
raw=path.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='52c06a53be31d77e2f32004b103a80235188edde4a61db703cc2cd027bf8bebb','Unexpected registry; do not replay.'
data=json.loads(raw)
before=ROOT/'reports/mpr-precision-20260910/before-action-location.json'
assert not before.exists()
before.write_bytes(raw)
for year,header_page in [(2023,439),(2024,445)]:
    text=(ROOT/f'reports/reserves-et-consignes-20260909/rap-ecologie-{year}.txt').read_text(encoding='utf-8').split('\f')[header_page-1]
    assert 'ACTION\n 02 – Accompagnement transition énergétique' in text
    matched=[r for r in data['facts'] if r['year']==year and r['stage']=='EXEC' and r['program']=='174']
    assert len(matched)==2 and all(r['precision']=='1 € (RAP)' for r in matched)
    for r in matched:
        r.update(action='02',action_label='Accompagnement transition énergétique',allocation_header_page=header_page)
    timeline=next(r for r in data['timeline'] if r['year']==year)
    timeline['note']+=' Le consommé MaPrimeRénov’ du P174 est rattaché à l’action 02 dans le RAP.'
data['limitations'].append('Le rattachement à l’action 02 est documenté pour le consommé P174 2023–2024 uniquement ; aucune ventilation de LFI, crédits ouverts ou réserve n’en est déduite.')
path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('4 rattachements action 02 ; aucun montant ni document modifié.')
