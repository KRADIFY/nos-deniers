import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
topic_path = root / "budget_service/data/maprimerenov.json"
data = json.loads(topic_path.read_text(encoding="utf-8"))

source_id = "0bda7f84a57258b9143c"
source_url = "https://www2.assemblee-nationale.fr/static/17/Annexes-DL/PLF2025-Jaunes/28%20-Jaune_renovation_energ%C3%A9tique_batiments.pdf"
rows = [
    ("TA", "Écologie, développement et mobilité durables", "174", "Énergie, climat et après-mines", 0, "0"),
    ("PR", "Plan de relance", "362", "Écologie", 0, "0"),
    ("VA", "Cohésion des territoires", "135", "Urbanisme, territoires et amélioration de l’habitat", 137800000000, "1 378"),
]
new_facts = []
for mission, mission_label, program, program_label, cents, published in rows:
    new_facts.append({
        "year": 2025, "stage": "PLF", "measure": "CP", "budget": "BG",
        "mission": mission, "mission_label": mission_label,
        "program": program, "program_label": program_label,
        "action": "", "action_label": "", "subaction": "", "subaction_label": "",
        "category": "", "title": "", "cents": cents, "source": source_id,
        "line": 18, "page": 18,
        "field": f"Tableau page 18 · 2025 PLF · CP · P{program}",
        "published_value": published, "published_unit": "M€",
        "precision": "1 M€", "approximate": 1,
        "basis": "Crédits de paiement proposés au PLF 2025 pour financer MaPrimeRénov’ (prime de transition énergétique), selon le tableau publié."
    })

data["facts"] = [
    r for r in data["facts"]
    if not (r["year"] == 2025 and r["stage"] == "PLF" and r["measure"] == "CP")
] + new_facts
data["coverage"] = [
    r for r in data["coverage"]
    if not (r["year"] == 2025 and r["stage"] == "PLF" and r["measure"] == "CP")
] + [{
    "year": 2025, "stage": "PLF", "measure": "CP",
    "paths": ["TA/174", "PR/362", "VA/135"],
    "basis": "Jaune budgétaire Rénovation énergétique 2025, p. 18 : tableau national complet des CP MaPrimeRénov’ proposés au PLF 2025, P174 = 0 M€, P362 = 0 M€, P135 = 1 378 M€."
}]

if not any(r.get("source") == source_id and r.get("page") == 18 for r in data["references"]):
    data["references"].append({
        "source": source_id, "page": 18,
        "label": "Jaune budgétaire 2025 · CP MaPrimeRénov’ proposés au PLF par programme",
        "url": source_url
    })

for item in data["timeline"]:
    if item["year"] == 2025:
        item["stages"] = ["PLF"]
        item["note"] = ("PLF 2025 : 1 378 M€ de CP proposés pour MaPrimeRénov’, entièrement portés par le P135 ; "
                        "les zéros P174 et P362 sont publiés dans le même tableau. Pour la mission Écologie, "
                        "l’exclusion sans retrait monétaire en LFI et consommé reste justifiée par le transfert "
                        "et le rapprochement du RAP P174. Les autres étapes 2025 ne sont pas isolées.")
        if not any(r.get("source") == source_id and r.get("page") == 18 for r in item["references"]):
            item["references"].insert(0, {"source": source_id, "page": 18})

data["availability_note"] = (
    "Ensemble des missions : consommé 2021–2024, voté et crédits ouverts 2024, ainsi que CP proposés au PLF 2025. "
    "Écologie : MaPrimeRénov’ du P174 chiffrée aussi en LFI et consommé 2020 ; exclusion 2025 justifiée en LFI "
    "et consommé par le transfert au P135. Les autres montants 2025 restent à isoler."
)
data["limitations"][2] = (
    "Restent à isoler : périmètre national complet de 2020 ; AE, LFI, crédits ouverts, consommé et mouvements "
    "détaillés 2025 ; tous les montants 2026 ; ainsi que les étapes encore absentes des années antérieures. "
    "Le PLF 2025 CP est disponible. Aucun gel n’est déduit du non-consommé."
)
data["limitations"][5] = (
    "En 2025, le tableau du jaune budgétaire publie pour le PLF 1 378 M€ de CP sur le P135 et 0 M€ sur les P174 "
    "et P362. Pour les AE, la LFI et le consommé, l’absence de retrait au P174 résulte du transfert et du "
    "rapprochement documentés ; elle ne donne pas le montant national de ces étapes et ne convertit aucun blanc en zéro."
)
data["updated_at"] = "2026-09-20"
topic_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

topics_test = root / "tests/test_topics.py"
text = topics_test.read_text(encoding="utf-8")
text = text.replace("self.assertEqual(len(topics.registry()['facts']),36)",
                    "self.assertEqual(len(topics.registry()['facts']),39)")
topics_test.write_text(text, encoding="utf-8")

mpr_test = root / "tests/test_mpr_perimeter.py"
text = mpr_test.read_text(encoding="utf-8")

def replace_method(name, following_name, body):
    global text
    pattern = rf"    def {re.escape(name)}\(self\):\n.*?(?=    def {re.escape(following_name)}\(self\):)"
    updated, count = re.subn(pattern, body.rstrip() + "\n\n", text, flags=re.S)
    if count == 0:
        return
    if count != 1:
        raise RuntimeError(f"Unable to replace {name}: {count}")
    text = updated

replace_method(
    "test_2025_zero_is_a_perimeter_result_not_an_imported_fact",
    "test_2025_perimeter_evidence_never_extrapolates_to_other_scopes_years_or_stages",
'''    def test_2025_transfer_evidence_and_published_plf_cp_are_distinct(self):
        facts = [r for r in topics.registry()['facts'] if r['year'] == 2025]
        self.assertEqual(len(facts), 3)
        self.assertEqual({(r['mission'], r['program']): r['cents'] for r in facts},
                         {('TA', '174'): 0, ('PR', '362'): 0, ('VA', '135'): 137800000000})
        self.assertEqual({(r['stage'], r['measure']) for r in facts}, {('PLF', 'CP')})
        self.assertTrue(all(r['source'] == '0bda7f84a57258b9143c' and r['page'] == 18 for r in facts))

        # The transfer evidence remains a non-monetary perimeter statement for
        # AE, LFI and execution. It must not manufacture a national zero.
        for stage, measure in (('PLF', 'AE'), ('LFI', 'AE'), ('LFI', 'CP'),
                               ('EXEC', 'AE'), ('EXEC', 'CP')):
            expected = self.evidence_citations(stage, measure)
            for scope in ('TA', 'TA/174', 'TA/174/02'):
                with self.subTest(stage=stage, measure=measure, scope=scope):
                    cell = topics.subset(scope, 2025, stage, dict(self.p, measure=measure), {})
                    self.assertEqual((cell['value'], cell['nominal_cents'], cell['count'], cell['status']),
                                     (0, 0, 0, 'ok'))
                    self.assertEqual({(c['source'], c['page']) for c in cell['citations']}, expected)

        # CP at PLF is a published table: the programme-level zero is explicit.
        for scope, count in (('TA', 1), ('TA/174', 1), ('TA/174/02', 0)):
            cell = topics.subset(scope, 2025, 'PLF', dict(self.p, measure='CP'), {})
            self.assertEqual((cell['value'], cell['nominal_cents'], cell['count'], cell['status']),
                             (0, 0, count, 'ok'))
            if count:
                self.assertIn({'source': '0bda7f84a57258b9143c', 'page': 18}, cell['citations'])''')

replace_method(
    "test_2025_perimeter_evidence_never_extrapolates_to_other_scopes_years_or_stages",
    "test_2025_without_preserves_base_amount_count_and_adds_documentary_citations",
'''    def test_2025_perimeter_evidence_never_extrapolates_to_other_scopes_years_or_stages(self):
        expected_plf_cp = {
            '': 1378000000, 'VA': 1378000000, 'VA/135': 1378000000,
            'PR': 0, 'PR/362': 0,
        }
        for scope, amount in expected_plf_cp.items():
            with self.subTest(scope=scope):
                cell = topics.subset(scope, 2025, 'PLF', dict(self.p, measure='CP'), {})
                self.assertEqual((cell['value'], cell['status']), (amount, 'ok'))
                self.assertIn({'source': '0bda7f84a57258b9143c', 'page': 18}, cell['citations'])

        for scope in ('', 'VA', 'VA/135', 'PR', 'PR/362'):
            for stage, measure in (('PLF', 'AE'), ('LFI', 'AE'), ('LFI', 'CP'),
                                   ('EXEC', 'AE'), ('EXEC', 'CP')):
                with self.subTest(scope=scope, stage=stage, measure=measure):
                    self.assertIsNone(topics.subset(scope, 2025, stage,
                                                   dict(self.p, measure=measure), {})['value'])
        for year, stages in ((2025, ('OUVERT', 'FDC', 'REPORT_ENTRANT')),
                             (2026, ('PLF', 'LFI', 'EXEC', 'OUVERT'))):
            for stage in stages:
                self.assertIsNone(topics.subset('TA', year, stage, self.p, {})['value'])''')

replace_method(
    "test_2025_without_preserves_base_amount_count_and_adds_documentary_citations",
    "test_missing_base_cannot_be_replaced_by_documented_zero_subtraction",
'''    def test_2025_without_preserves_base_amount_and_zero_subtraction(self):
        for stage, measure in (('PLF', 'AE'), ('PLF', 'CP'), ('LFI', 'AE'), ('LFI', 'CP'),
                               ('EXEC', 'AE'), ('EXEC', 'CP')):
            with self.subTest(stage=stage, measure=measure):
                rows = [parent(12000000123, stage=stage, measure=measure),
                        parent(5000000045, stage=stage, measure=measure, program='203')]
                p = dict(self.p, topic_mode='without', measure=measure)
                base = api.cell(rows, 'TA', 2025, stage, p, {})
                base['citations'] = [{'source': 'parent-csv', 'page': 42}]
                before = copy.deepcopy(base)
                cell = topics.calculate(rows, base, 'TA', 2025, stage, p, {})
                for key in ('value', 'nominal', 'nominal_cents', 'status'):
                    self.assertEqual(cell[key], base[key], key)
                self.assertEqual(cell['count'], base['count'] + (1 if (stage, measure) == ('PLF', 'CP') else 0))
                self.assertEqual(cell['topic_subtracted_nominal'], 0)
                expected = self.evidence_citations(stage, measure) | {('parent-csv', 42)}
                if (stage, measure) == ('PLF', 'CP'):
                    expected.add(('0bda7f84a57258b9143c', 18))
                self.assertEqual({(c['source'], c['page']) for c in cell['citations']}, expected)
                self.assertEqual(base, before)''')

mpr_test.write_text(text, encoding="utf-8")

audit_path = root / "budget_service/audit_data.py"
audit = audit_path.read_text(encoding="utf-8")
marker = "    report={'built_at':meta['built_at']"
if "mpr2025_plf_cp_checks" not in audit:
    block = '''    topic=json.loads((Path(__file__).parent/'data/maprimerenov.json').read_text(encoding='utf-8'))
    mpr2025=[r for r in topic['facts'] if (r['year'],r['stage'],r['measure'])==(2025,'PLF','CP')]
    expected_mpr2025={('TA','174'):0,('PR','362'):0,('VA','135'):137800000000}
    assert len(mpr2025)==3
    assert {(r['mission'],r['program']):r['cents'] for r in mpr2025}==expected_mpr2025
    assert all(r['source']=='0bda7f84a57258b9143c' and r['page']==18
               and r['published_unit']=='M€' and r['precision']=='1 M€' for r in mpr2025)
    mpr_coverage=[r for r in topic['coverage']
                  if (r['year'],r['stage'],r['measure'])==(2025,'PLF','CP')]
    assert len(mpr_coverage)==1 and set(mpr_coverage[0]['paths'])=={'TA/174','PR/362','VA/135'}
    mpr_source_id='0bda7f84a57258b9143c'
    stored=db.execute('SELECT data FROM sources WHERE id=?',(mpr_source_id,)).fetchone()
    assert stored,mpr_source_id
    mpr_source=json.loads(stored[0])
    assert mpr_source['sha256']=='b5e07637ba4a60d3cbab583f3bf0edd6524c03306efdbcc7d3844c872cc8a1a9'
    assert hashlib.sha256((DATA/mpr_source['path']).read_bytes()).hexdigest()==mpr_source['sha256']
    mpr2025_plf_cp_checks={'facts':len(mpr2025),'national_cp_cents':sum(r['cents'] for r in mpr2025),
                           'programmes':3,'published_zero_programmes':2,
                           'source_hashes_verified':1,'blank_cells_converted_to_zero':False,
                           'canonical_facts_rewritten':False}
'''
    if marker not in audit:
        raise RuntimeError("audit insertion marker missing")
    audit = audit.replace(marker, block + marker)
    old = "'rap_reserves_national_checks':rap_reserves_national,'checks':checks}"
    new = "'rap_reserves_national_checks':rap_reserves_national,'mpr2025_plf_cp_checks':mpr2025_plf_cp_checks,'checks':checks}"
    if old not in audit:
        raise RuntimeError("audit report marker missing")
    audit = audit.replace(old, new)
audit_path.write_text(audit, encoding="utf-8")

print(json.dumps({
    "facts": len(data["facts"]), "coverage": len(data["coverage"]),
    "mpr_2025_facts": len(new_facts), "updated_at": data["updated_at"]
}, ensure_ascii=False))
