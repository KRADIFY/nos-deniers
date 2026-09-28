"""Document reviewed gaps; never generate monetary facts from a missing table."""
import hashlib
import json
import sqlite3
from pathlib import Path
import fitz
from rap_program_context import programme_context

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/rap-limits-20260920'


def main():
    audit = json.loads((ROOT / 'reports/recovery-20260920/provenance-audit.json').read_text(encoding='utf8'))
    sources = json.loads((ROOT / 'reports/recovery-20260920/actions/sources.json').read_text(encoding='utf8'))
    gaps = {kind: {tuple(k) for k in audit['coverage'][field]} for kind, field in
            [('reserves', 'without_reserve_table'), ('movements', 'without_movement_recap')]}
    wanted = set.union(*gaps.values())
    db = sqlite3.connect('file:' + (ROOT / 'reports/mpr-closure-20260920/runtime/derived/budget.sqlite').as_posix() + '?mode=ro', uri=True)
    rows, public_sources, checks = [], [], []
    for source in sources:
        keys = sorted(k for k in wanted if k[:2] == (source['year'], source['mission']))
        if not keys:
            continue
        path = Path(source['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
        metadata = json.loads(db.execute('SELECT data FROM sources WHERE id=?', (source['source'],)).fetchone()[0])
        assert metadata['sha256'] == source['sha256']
        public_sources.append({k: metadata.get(k) for k in ('id', 'title', 'sha256', 'url', 'format')})
        text = Path(source['text_path']).read_text(encoding='utf8')
        pages, contexts = text.split('\f'), programme_context(text)
        with fitz.open(path) as pdf:
            for year, mission, program in keys:
                numbers = [i for i in range(1, len(pdf)+1) if contexts[i]['program'] == program]
                assert numbers
                first, last = min(numbers), max(numbers)
                physical = ' '.join(pdf[first-1].get_text().split())
                assert 'PROGRAMME ' + program in physical
                label = db.execute('SELECT program_label FROM facts WHERE year=? AND mission=? AND program=? LIMIT 1', (year, mission, program)).fetchone()
                row = dict(year=year, budget='BG', mission=mission, program=program,
                           program_label=label[0] if label else contexts[first]['label'],
                           source=source['source'], sha256=source['sha256'], page=first,
                           page_end=last, context_pages=[first], missing=[kind for kind in gaps if (year,mission,program) in gaps[kind]])
                if (year, mission, program) == (2025, 'AD', '384'):
                    assert 'aucune mesure de mise en réserve' in ' '.join(pdf[145].get_text().split())
                    row.update(reserve_status='not_applicable', page=146, context_pages=[first,146],
                        reserve_note='Le RAP indique explicitement que le P384 n’est soumis à aucune mesure de mise en réserve ni à aucune régulation budgétaire. Cette exemption ne signifie pas absence de reports ou de tout autre mouvement.',
                        movement_note='Le RAP indique une exemption de régulation budgétaire et des reports automatiques. Il ne fournit pas ici une récapitulation datée des mouvements à intégrer.')
                    pdf[145].get_pixmap(matrix=fitz.Matrix(1.15,1.15)).save(REPORT/'exemption-p384-2025.png')
                elif (year, mission, program) == (2023, 'AD', '370'):
                    assert 'Aucune ouverture de crédit sur le programme' in ' '.join(pdf[158].get_text().split())
                    row.update(page=159, context_pages=[first,159], movement_note='Le RAP indique qu’aucune ouverture de crédit n’a eu lieu sur ce programme en 2023. Ce constat est conservé comme explication documentaire ; il ne crée pas une fausse opération datée à zéro.')
                    pdf[158].get_pixmap(matrix=fitz.Matrix(1.15,1.15)).save(REPORT/'sans-ouverture-p370-2023.png')
                elif (year, mission, program) == (2024, 'AD', '370'):
                    assert '13 mars 2025' in pdf[167].get_text()
                    row.update(page=168, context_pages=[first,168], movement_note='Le RAP décrit les crédits ouverts en LFI 2024 puis intégralement reportés par arrêté du 13 mars 2025. Ce report relève de 2025 ; il n’est pas transformé en mouvement daté de 2024.')
                rows.append(row)
                checks.append(dict(year=year, mission=mission, program=program, first_page=first, last_page=last, physical_opening_verified=True))
    db.close()
    result = dict(checked_at='2026-09-20', scope=audit['coverage']['scope'],
                  audited_programme_years=379, sources=public_sources, gaps=rows)
    target = ROOT / 'budget_service/data/rap-coverage.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    receipt = dict(success=True, programme_years=len(rows), reserve_gaps=len(gaps['reserves']), movement_gaps=len(gaps['movements']),
                   sources_verified=len(public_sources), checks=checks, sha256=hashlib.sha256(target.read_bytes()).hexdigest(), monetary_facts_added=0)
    (REPORT/'coverage-proof.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='checks'}, ensure_ascii=False))


if __name__ == '__main__':
    REPORT.mkdir(parents=True, exist_ok=True)
    main()
