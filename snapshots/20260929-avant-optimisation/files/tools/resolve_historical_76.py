"""One-time, idempotent integration of the sixty qualified historical cells.

Thirty-two 2017 P186/P190 management facts are added. Forty-four 2020 P307/P333
printed zeros are explained as non-applicable after merger into P354, never
inserted as active-program facts. Existing amounts are preserved byte for byte.
"""
import collections,hashlib,json,os,shutil,sqlite3,sys
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDITOR=ROOT/'auditeur-independant'
sys.path.insert(0,str(AUDITOR))
from coverage import scan_annex,sha

BASE=ROOT/'deploy/update-20260928-controles/data'
OUT=ROOT/'reports/historical-76-20260929'
TARGET=OUT/'data'
EXPECTED_DB='aa11479b90fb9c2d79003234b0223cc2a25198fb09c10f4ac2ef4c5ced5da7ba'
MERGER='https://www.budget.gouv.fr/documentation/file-download/4155'
STAGES=('LEGIS','REPORT_ENTRANT','REGLEMENT','FDC','FONGIBILITE',
        'PLRG_OUVERTURE','PLRG_ANNULATION','REPORT_SORTANT')


def main():
    receipt=OUT/'receipt.json'
    if receipt.exists():
        done=json.loads(receipt.read_text('utf-8'))
        assert sha(TARGET/'derived/budget.sqlite')==done['database_sha256']
        print(json.dumps(done,ensure_ascii=False));return
    assert sha(BASE/'derived/budget.sqlite')==EXPECTED_DB
    contract=json.loads((AUDITOR/'document-coverage.json').read_text('utf-8'))
    scans={}
    for year in (2017,2020):
        src=next(s for s in contract['sources'] if s['year']==year)
        pdf=BASE/src['path']
        assert sha(pdf)==src['sha256']
        scan=scan_annex(pdf,src)
        assert not [x for x in scan['problems'] if x.get('program') in ('186','307','333')]
        scans[year]=(src,scan)
    active=[r for r in scans[2017][1]['rows'] if r['program'] in ('186','190')]
    retired=[r for r in scans[2020][1]['rows'] if r['program'] in ('307','333')]
    assert {(r['measure'],r['program']) for r in active}=={(m,p) for m in ('AE','CP') for p in ('186','190')}
    assert {(r['measure'],r['program']) for r in retired}=={(m,p) for m in ('AE','CP') for p in ('307','333')}
    assert len(active)*len(STAGES)==32 and len(retired)*11==44
    for r in active:
        c=r['cells']
        assert sum(c[s]['cents'] for s in ('LFI','LEGIS','REPORT_ENTRANT','REGLEMENT','FDC','FONGIBILITE'))==c['OUVERT']['cents']
        assert c['OUVERT']['cents']+c['PLRG_OUVERTURE']['cents']==sum(c[s]['cents'] for s in ('EXEC','PLRG_ANNULATION','REPORT_SORTANT'))
    assert all(c['cents']==0 for r in retired for c in r['cells'].values())
    for src in BASE.rglob('*'):
        if src.is_symlink():raise ValueError('Lien symbolique inattendu dans la base de départ')
        rel=src.relative_to(BASE);dest=TARGET/rel
        if src.is_dir():dest.mkdir(parents=True,exist_ok=True)
        elif rel.as_posix() not in ('derived/budget.sqlite','derived/data-audit.json'):
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():os.link(src,dest)
    dbpath=TARGET/'derived/budget.sqlite';dbpath.parent.mkdir(parents=True,exist_ok=True)
    if dbpath.exists():raise ValueError('Base préparée sans reçu : inspection nécessaire')
    build=dbpath.with_suffix('.build.sqlite')
    if build.exists():raise ValueError('Préparation précédente à inspecter')
    shutil.copyfile(BASE/'derived/budget.sqlite',build)
    with closing(sqlite3.connect(build)) as db, db:
        db.row_factory=sqlite3.Row
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        fields=[r['name'] for r in db.execute('pragma table_info(facts)')]
        assert len(fields)==19
        catalog={r['id']:json.loads(r['data']) for r in db.execute('select * from sources')}
        for year in (2017,2020):
            src=scans[year][0];assert catalog[src['id']]['sha256']==src['sha256']
        peers={p:dict(db.execute('select * from facts where year=2017 and budget="BG" and program=? limit 1',(p,)).fetchone()) for p in ('186','190')}
        assert peers['186']['mission']=='RA' and peers['190']['mission']=='RA'
        former={p:dict(db.execute('select * from facts where year=2019 and budget="BG" and program=? limit 1',(p,)).fetchone()) for p in ('307','333')}
        assert former['307']['mission']=='AB' and former['333']['mission']=='DC'
        assert db.execute('select count(*) from facts where year=2020 and program in ("307","333")').fetchone()[0]==0
        facts=[];reviews=[]
        for row in active:
            peer=peers[row['program']];src=catalog[row['source']];path='RA/'+row['program']
            for stage in STAGES:
                cell=row['cells'][stage];key=(2017,stage,row['measure'],'BG',path)
                assert db.execute('select 1 from cell_reviews where year=? and stage=? and measure=? and budget=? and path=?',key).fetchone() is None
                assert db.execute('select 1 from facts where year=2017 and stage=? and measure=? and budget="BG" and mission="RA" and program=?', (stage,row['measure'],row['program'])).fetchone() is None
                proof=dict(source_id=row['source'],sha256=row['sha256'],physical_page=cell['page'],
                    evidence=f"P{row['program']} · 2017 · {row['measure']} · {stage} · ligne Total : {cell['raw']} €",
                    publisher_url=src.get('url',''),bbox=cell['bbox'],raw_text=cell['raw'],unit='EUR')
                review=dict(year=2017,stage=stage,measure=row['measure'],budget='BG',path=path,status='verified',
                    method='Annexe PLR 2017 relue directement ; identité des crédits ouverts et du solde de clôture contrôlée.' + (' Code 190 corroboré par le RAP officiel : https://www.budget.gouv.fr/sites/performance_publique/files/farandole/ressources/2017/rap/pdf/DRGPGMPGM190.pdf' if row['program']=='190' else ''),
                    explanation=f"Programme {row['program']} en 2017, {row['measure']}, {stage} : {cell['raw']} € à la page {cell['page']}. Le total LFI, ouvert et consommé déjà intégré est conservé.",
                    proofs=[proof],source_cents=cell['cents'],batch='historical-76-20260929')
                reviews.append(review)
                fact={k:'' for k in fields}
                fact.update(year=2017,stage=stage,measure=row['measure'],budget='BG',mission='RA',mission_label=peer['mission_label'],
                    program=row['program'],program_label=peer['program_label'],cents=cell['cents'],source=row['source'],line=cell['page'],
                    field='Annexe PLR 2017 · total du programme · '+stage+' (EUR)',approximate=0)
                facts.append(fact)
        for row in retired:
            peer=former[row['program']];src=catalog[row['source']];path=peer['mission']+'/'+row['program']
            for stage,cell in row['cells'].items():
                key=(2020,stage,row['measure'],'BG',path)
                assert db.execute('select 1 from cell_reviews where year=? and stage=? and measure=? and budget=? and path=?',key).fetchone() is None
                proof=dict(source_id=row['source'],sha256=row['sha256'],physical_page=cell['page'],
                    evidence=f"Ancien P{row['program']} · 2020 · {row['measure']} · {stage} : zéro imprimé dans la ligne Total.",
                    publisher_url=src.get('url',''),bbox=cell['bbox'],raw_text=cell['raw'],unit='EUR')
                review=dict(year=2020,stage=stage,measure=row['measure'],budget='BG',path=path,status='not_applicable',
                    method='Zéro imprimé dans l’annexe PLR 2020, vérifié par empreinte. Fusion des programmes 307 et 333 dans le 354 au 1er janvier 2020 : '+MERGER,
                    explanation=f"L’ancien programme {row['program']} n’est plus un poste autonome en 2020 : fusion dans le programme 354. Le zéro imprimé page {cell['page']} est conservé comme preuve historique, pas comme un montant actif à additionner.",
                    proofs=[proof],source_cents=0,batch='historical-76-20260929',successor_program='354',merger_source_url=MERGER)
                reviews.append(review)
        assert len(facts)==32 and len(reviews)==76
        db.executemany('insert into facts values('+','.join('?' for _ in fields)+')',[tuple(f[k] for k in fields) for f in facts])
        db.executemany('insert into cell_reviews values (?,?,?,?,?,?)',[(r['year'],r['stage'],r['measure'],r['budget'],r['path'],json.dumps(r,ensure_ascii=False)) for r in reviews])
        count=db.execute('select count(*) from facts').fetchone()[0]
        assert count==135187
        stats={f'{y}/{st}/{b}':n for y,st,b,n in db.execute('select year,stage,budget,count(*) from facts group by year,stage,budget')}
        old_version=json.loads(db.execute('select value from meta where key="data_version"').fetchone()[0])
        fingerprint=hashlib.sha256(json.dumps(dict(facts=facts,reviews=reviews),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        new_version=hashlib.sha256((old_version+fingerprint).encode()).hexdigest()
        updates=dict(fact_count=count,stats=stats,data_version=new_version,
                     historical_76_review=dict(added_facts=32,retired_cells_documented=44,
                                               source_2017_sha256=scans[2017][0]['sha256'],
                                               source_2020_sha256=scans[2020][0]['sha256'],
                                               prior_data_version=old_version))
        for key,value in updates.items():db.execute('insert or replace into meta(key,value) values(?,?)',(key,json.dumps(value,ensure_ascii=False)))
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert db.execute('select count(*) from cell_reviews').fetchone()[0]==12704
    build.replace(dbpath)
    done=dict(database_sha256=sha(dbpath),base_sha256=EXPECTED_DB,data_version=new_version,
              fact_count=135187,review_count=12704,added_facts=32,retired_cells_documented=44,
              p186_nonzero=sum(f['cents']!=0 and f['program']=='186' for f in facts),p186_zero=sum(f['cents']==0 and f['program']=='186' for f in facts),
              p190_nonzero=sum(f['cents']!=0 and f['program']=='190' for f in facts),p190_zero=sum(f['cents']==0 and f['program']=='190' for f in facts),
              pdf_issues_2017=scans[2017][1]['problems'])
    receipt.write_text(json.dumps(done,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(done,ensure_ascii=False))

if __name__=='__main__':main()
