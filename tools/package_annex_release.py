"""Prepare a cumulative deployment, preserving the previous publication bundle."""
import collections
import json
import shutil
import sqlite3
from pathlib import Path
from integrate_researched_annexes import ROOT, OUT as WORK, TARGET, read, dump, sha

OUT = ROOT / 'deploy/update-20260928-annexes'
PREVIOUS = ROOT / 'deploy/update-20260928-classeurs'


def copy(src, relative):
    dest = OUT / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def main():
    verification = read(WORK / 'verification.json')
    classification = read(WORK / 'independent-classification.json')
    assert verification['passed'] and classification['new_integration_passed']
    assert read(WORK / 'browser.json')['passed']
    assert not (OUT / 'release.json').exists(), 'Paquet déjà figé : ne pas écraser une livraison'
    receipt = read(WORK / 'receipt.json')
    before = read(PREVIOUS / 'plan.json')
    latest = read(WORK / 'plan.json')
    assert sha(TARGET / 'derived/budget.sqlite') == receipt['database_sha256']
    combined = dict(before)
    combined['facts'] = before['facts'] + latest['facts']
    key = lambda r: tuple(r[k] for k in ('year', 'stage', 'measure', 'budget', 'path'))
    reviews = {key(r): r for r in before['reviews']}
    reviews.update({key(r): r for r in latest['reviews']})
    combined['reviews'] = list(reviews.values())
    combined['verified_sources'] = dict(before['verified_sources'])
    combined['annex_sources'] = latest['source_evidence']
    for sid, r in latest['source_evidence'].items():
        combined['verified_sources'][sid] = dict(path=r['path'], sha256=r['sha256'])
    for name in ('api.py', 'cell_reviews.py'):
        copy(ROOT / 'budget_service' / name, 'app/budget_service/' + name)
    for name in ('explorer.html', 'assets/explorer.css', 'assets/explorer.js'):
        copy(ROOT / 'public' / name, 'app/public/' + name)
    copy(ROOT / 'tests/test_workbook_cell_reviews.py', 'app/tests/test_workbook_cell_reviews.py')
    install = (ROOT / 'tools/install_workbook_release.py').read_text('utf-8')
    install = install.replace('20260928-classeurs', '20260928-annexes').replace('fact_count=123483', "fact_count=contract['fact_count']")
    (OUT / 'install.py').write_text(install, 'utf-8')
    copy(ROOT / 'tools/annex_release_verify.py', 'verify.py')
    dump(OUT / 'plan.json', combined)
    data_files = ['derived/budget.sqlite'] + [r['path'] for r in before['new_sources']] + [r['path'] for r in latest['source_evidence'].values()]
    assert len(set(data_files)) == len(data_files)
    for relative in data_files:
        copy(TARGET / relative, 'data/' + relative)
    for name in ('verification.json', 'independent-oracle.json', 'independent-classification.json', 'browser.json', 'unit-tests.log'):
        copy(WORK / name, 'checks/' + name)
    (OUT / 'Dockerfile').write_text('ARG BASE\nFROM ${BASE}\nCOPY app/ /app/\n', 'utf-8')
    (OUT / 'PUBLIER_SUR_VPS.sh').write_text('#!/bin/sh\nset -eu\ncd /home/marie/nos-deniers-update-20260928-annexes\nexec sudo python3 ./install.py "$@"\n', 'utf-8')
    contract = dict(release='20260928-annexes', data_version=receipt['data_version'],
                    database_sha256=receipt['database_sha256'], baseline_sha256=before['baseline_sha256'],
                    fact_count=receipt['fact_count'], added_facts=len(combined['facts']),
                    review_count=len(combined['reviews']), data_files=data_files,
                    annex_sources=list(latest['source_evidence']), preexisting_source_alerts=classification['preexisting_source_alerts'],
                    files={p.relative_to(OUT).as_posix(): sha(p) for p in OUT.rglob('*') if p.is_file() and p.name != 'release.json'})
    # Validate the entire cumulative delta against the unchanged public predecessor.
    db = sqlite3.connect(TARGET / 'derived/budget.sqlite')
    old = sqlite3.connect((ROOT / 'reports/release-20260924-working/data/derived/budget.sqlite').as_uri() + '?mode=ro', uri=True)
    fields = [r[1] for r in old.execute('pragma table_info(facts)')]
    rows = lambda c: collections.Counter(c.execute('select * from facts').fetchall())
    added = collections.Counter(tuple(r[k] for k in fields) for r in combined['facts'])
    removed = collections.Counter(tuple(r[k] for k in fields) for r in combined['removed_duplicate_zeroes'])
    assert rows(db) == rows(old) + added - removed
    db.close(); old.close()
    dump(OUT / 'release.json', contract)
    print(json.dumps(dict(folder=str(OUT), facts=contract['fact_count'], cumulative_additions=contract['added_facts'],
                         reviews=contract['review_count'], files=len(contract['files']),
                         transferred=False, published=False), ensure_ascii=False))


if __name__ == '__main__':
    main()
