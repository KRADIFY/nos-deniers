"""Checks every imported cell against the frozen plan and the site calculation."""
import collections
import hashlib
import json
import os
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/integration-classeurs-20260928'
os.environ.setdefault('BUDGET_DATA_DIR',str(OUT/'data'))
from budget_service import api

def run():
    plan=json.loads((OUT/'plan.json').read_text('utf-8'))
    db=api.connect();baseline=sqlite3.connect((ROOT/'reports/release-20260924-working/data/derived/budget.sqlite').as_uri()+'?mode=ro',uri=True)
    def counter(c):return collections.Counter(c.execute('select * from facts').fetchall())
    fields=[x[1] for x in baseline.execute('pragma table_info(facts)')]
    old=counter(baseline);now=collections.Counter(tuple(r) for r in db.execute('select * from facts'))
    added=collections.Counter(tuple(r[k] for k in fields) for r in plan['facts'])
    removed=collections.Counter(tuple(r[k] for k in fields) for r in plan['removed_duplicate_zeroes'])
    assert now==old+added-removed,'Unrequested changes in canonical facts'
    cached={};checked=collections.Counter();proofs=set();exclusions=0
    for review in plan['reviews']:
        key=(review['year'],review['budget'],review['measure'])
        if key not in cached:
            p=api.parameters({k:[str(v)] for k,v in dict(start=key[0],end=key[0],budget=key[1],measure=key[2]).items()})
            cached[key]=(p,api.selected_records(db,p))
        p,records=cached[key]
        result=api.cell(records,review['path'],review['year'],review['stage'],p,{},reviews=records.cell_reviews)
        if review['status']=='verified':
            wanted=next(f for f in plan['facts'] if (f['year'],f['budget'],f['measure'],f['stage'],f['mission']+'/'+f['program'])==(review['year'],review['budget'],review['measure'],review['stage'],review['path']))
            assert result['nominal_cents']==wanted['cents'],(review,result,wanted)
            assert result['value']==wanted['cents']/100
            excluded=api.cell(records,review['path'],review['year'],review['stage'],dict(p,exclude=[review['path']]),{},reviews=records.cell_reviews)
            assert excluded['value']==0 and excluded['status']=='excluded'
            exclusions+=1
            for proof in review['proofs']:
                assert any(c['source']==proof['source_id'] and c['page']==proof['physical_page'] for c in result['citations'])
        else:
            assert result['value'] is None,(review,result)
            assert result['status']==('not_applicable' if review['status']=='not_applicable' else 'missing')
        checked[review['status']]+=1
        for proof in review['proofs']: proofs.add((proof['source_id'],proof['sha256']))
    for sid,digest in proofs:
        source=api.source(db,sid);p=Path(api.DATA)/source['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
    # Read actual provenance including the multi-document and unknown cases.
    examples=[next(r for r in plan['reviews'] if r['status']==status) for status in ('verified','not_applicable','pending')]
    examples+=[next(r for r in plan['reviews'] if any(p['physical_page'] is None for p in r['proofs']))]
    for r in examples:
        p,_=cached[(r['year'],r['budget'],r['measure'])]
        got=api.provenance(db,p,r['year'],r['stage'],r['path'])
        assert got['explanation']['summary']==r['explanation']
        assert all(p['source_id'] in {s['id'] for s in got['sources']} for p in r['proofs'])
    result=dict(passed=True,checked=dict(checked),exclusions_checked=exclusions,source_hashes_verified=len(proofs),
                facts=api.metadata(db)['fact_count'],data_version=api.metadata(db)['data_version'],
                previous_facts_preserved_except_four_documented_duplicate_zeroes=True)
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(result))
    db.close();baseline.close()
if __name__=='__main__':run()
