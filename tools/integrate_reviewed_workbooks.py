"""Reproducible, additive import of the two reviewed workbooks; never edit the baseline."""
import collections
import hashlib
import json
import os
import re
import shutil
import sqlite3
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/integration-classeurs-20260928'
BASE = ROOT / 'reports/release-20260924-working/data'
TARGET = OUT / 'data'

def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    inventory = json.loads((OUT / 'inventory.json').read_text('utf-8'))
    assert inventory['counts'] == {'numeric_cells': 517, 'absent': 517}
    assert not inventory['conflicts']
    baseline_sha = sha(BASE / 'derived/budget.sqlite')
    if (OUT / 'receipt.json').exists():
        receipt = json.loads((OUT / 'receipt.json').read_text('utf-8'))
        assert sha(TARGET / 'derived/budget.sqlite') == receipt['database_sha256']
        print('Already staged and unchanged.'); return
    if TARGET.exists():
        assert sha(TARGET / 'derived/budget.sqlite') == baseline_sha, 'Unexpected partial database'
    # Existing public assets are immutable. The database and certificate are not linked.
    for src in BASE.rglob('*'):
        if not src.is_file() or src.name in ('budget.sqlite', 'data-audit.json'): continue
        dest = TARGET / src.relative_to(BASE); dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists(): os.link(src, dest)
    (TARGET / 'derived').mkdir(parents=True, exist_ok=True)
    if not (TARGET / 'derived/budget.sqlite').exists(): shutil.copy2(BASE / 'derived/budget.sqlite', TARGET / 'derived/budget.sqlite')
    (TARGET / 'derived/budget.sqlite').chmod(0o644)
    db = sqlite3.connect(TARGET / 'derived/budget.sqlite'); db.row_factory = sqlite3.Row
    catalog = {r['id']: json.loads(r['data']) for r in db.execute('select * from sources')}
    new_sources = []; verified = {}; aliases = {}
    for oldid, item in inventory['needed'].items():
        record = item['record']; proof = item['proof']
        if oldid == 'null':
            local = OUT / 'senat-plf2018.html'
            assert 'aucun crédit pour' in local.read_text('utf-8')
            record = dict(title=proof['title'], url='https://www.senat.fr/rap/l17-108-313/l17-108-3134.html',
                          sha256=sha(local), format='html', years_title=['2018'])
        else:
            candidates = [ROOT / f'outputs/verification-classeur{n}-20260928/pdf/{oldid}.pdf' for n in (10, 11)]
            candidates += [Path(record['local_file'])] if record.get('local_file') else []
            candidates += [BASE / record['path']] if record.get('path') else []
            local = next(p for p in candidates if p.is_file() and sha(p) == record['sha256'])
        sid = oldid if re.fullmatch('[a-f0-9]{20}', oldid) else hashlib.sha256(record['url'].encode()).hexdigest()[:20]
        aliases[oldid] = sid
        if sid not in catalog:
            record = dict(record, id=sid, path=f'public/reviews/20260928/{sid}.{record.get("format", "pdf")}',
                          role='official_document', status='downloaded', bytes=local.stat().st_size,
                          checked_at='2026-09-28', imported=True)
            record.pop('local_file', None)
            record.setdefault('years_title', [str(y) for y in sorted({r['year'] for r in inventory['rows'] if any(p['source_id'] == oldid for p in r['proofs'])})])
            catalog[sid] = record; new_sources.append(record)
            db.execute('insert into sources values (?,?)', (sid, json.dumps(record, ensure_ascii=False)))
        dest = TARGET / catalog[sid]['path']; dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists(): assert sha(dest) == record['sha256']
        else: shutil.copy2(local, dest)
        verified[sid] = dict(path=catalog[sid]['path'], sha256=sha(dest))
    db.execute('create table cell_reviews (year integer,stage text,measure text,budget text,path text,data text,primary key(year,stage,measure,budget,path))')
    fields = [r['name'] for r in db.execute('pragma table_info(facts)')]
    facts = []; reviews = []
    for row in inventory['rows']:
        numeric = row['status'] not in ('À confirmer', 'Absent du PLF initial', 'Périmètre à reclasser')
        proofs = []
        for original in row['proofs']:
            p = dict(original); sid = aliases[str(p['source_id']) if p['source_id'] is not None else 'null']
            p.update(source_id=sid, sha256=catalog[sid]['sha256'], publisher_url=catalog[sid]['url'])
            proofs.append(p)
        for measure in row['measures']:
            review = dict(year=row['year'], stage=row['stage'], measure=measure, budget=row['budget'], path=row['path'],
                          status='verified' if numeric else 'pending' if row['status']=='À confirmer' else 'not_applicable',
                          method=row['method'], explanation=row['explanation'], proofs=proofs,
                          workbook=row['workbook'], input_row=row['input_row'], original_status=row['status'])
            reviews.append(review)
            db.execute('insert into cell_reviews values (?,?,?,?,?,?)', tuple(review[k] for k in ('year','stage','measure','budget','path')) + (json.dumps(review,ensure_ascii=False),))
            if not numeric: continue
            mission,program=row['path'].split('/')
            fact=dict(year=row['year'],stage=row['stage'],measure=measure,budget=row['budget'],mission=mission,
                      mission_label=row['mission'],program=program,program_label=re.sub(r'^P\d+\s*[—–-]\s*','',row['label']),
                      action='',action_label='',subaction='',subaction_label='',category='',title='',
                      cents=int(Decimal(str(row[measure]))*100),source=proofs[0]['source_id'],line=proofs[0]['physical_page'] or 1,
                      field='Contrôle documentaire du 28/09/2026 : '+row['method'],approximate=0)
            assert not db.execute('select 1 from facts where year=? and stage=? and measure=? and budget=? and mission=? and program=?',tuple(fact[k] for k in ('year','stage','measure','budget','mission','program'))).fetchone()
            db.execute('insert into facts values ('+','.join('?' for _ in fields)+')',tuple(fact[k] for k in fields));facts.append(fact)
    # Four duplicate zero observations incorrectly classified as CAS; the exact CCF cells already exist.
    duplicates=[dict(r) for r in db.execute("select * from facts where year=2017 and budget='CAS' and mission='ZA' and program='811'")]
    assert len(duplicates)==4
    for r in duplicates:
        assert r['cents']==0 and r['stage'] in ('PLF','LFI')
        peers=list(db.execute("select cents from facts where year=2017 and budget='CCF' and mission='ZA' and program='811' and stage=? and measure=?",(r['stage'],r['measure'])))
        assert len(peers)==1 and peers[0]['cents']==0
    db.execute("delete from facts where year=2017 and budget='CAS' and mission='ZA' and program='811'")
    metadata_corrections=[]
    for sid in ('80bc3fc951fba990cc0f','d052be4a8d4c8900141b'):
        before=catalog[sid]; after=dict(before, title=before['title'].replace('2019','2020'),years_title=['2020'],
            catalogue_note='Millésime contrôlé dans le PDF : 2020. Ancien nom de fichier conservé pour traçabilité ; PAP 2019 distinct.')
        assert not db.execute('select 1 from facts where source=?',(sid,)).fetchone()
        db.execute('update sources set data=? where id=?',(json.dumps(after,ensure_ascii=False),sid))
        metadata_corrections.append(dict(id=sid,before=before,after=after))
    plan=dict(baseline_sha256=baseline_sha,facts=facts,reviews=reviews,removed_duplicate_zeroes=duplicates,
              new_sources=new_sources,source_metadata_corrections=metadata_corrections,verified_sources=verified)
    dump(OUT/'plan.json',plan)
    count=db.execute('select count(*) from facts').fetchone()[0]; assert count==123483
    stats={f'{y}/{s}/{b}':n for y,s,b,n in db.execute('select year,stage,budget,count(*) from facts group by year,stage,budget')}
    imported=db.execute('select count(distinct source) from facts').fetchone()[0]
    meta=dict(fact_count=count,stats=stats,imported_source_count=imported,source_count=db.execute('select count(*) from sources').fetchone()[0],
              data_version=hashlib.sha256((baseline_sha+sha(OUT/'plan.json')+json.dumps(stats,sort_keys=True)).encode()).hexdigest(),
              catalogue_updated_at='2026-09-28',workbook_review_20260928=dict(plan_sha256=sha(OUT/'plan.json'),added=517,duplicate_zeroes_removed=4,not_applicable=67,pending=64))
    for k,v in meta.items(): db.execute('insert or replace into meta values (?,?)',(k,json.dumps(v)))
    db.commit(); assert db.execute('pragma integrity_check').fetchone()[0]=='ok'; db.close()
    assert sha(BASE/'derived/budget.sqlite')==baseline_sha
    dump(OUT/'receipt.json',dict(**meta,database_sha256=sha(TARGET/'derived/budget.sqlite'),baseline_sha256=baseline_sha,
                               new_sources=len(new_sources),verified_sources=len(verified),plan_sha256=sha(OUT/'plan.json')))
    print(json.dumps(meta,ensure_ascii=False))

if __name__ == '__main__': main()
