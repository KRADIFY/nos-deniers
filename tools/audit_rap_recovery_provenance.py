"""Check programme boundaries and physical PDFs for the recovered registries."""
import hashlib,json,re
from pathlib import Path
import fitz
from rap_program_context import programme_context

ROOT=Path(__file__).resolve().parents[1];R=ROOT/'reports/recovery-20260920';D=ROOT/'budget_service/data'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    sources=read(R/'actions/sources.json');wanted={s['source']:set() for s in sources}
    for g in read(R/'actions/candidates.json')['groups']:
        pages={g['page'],g['total_page']}|{a['page'] for a in g['actions']}|{s['page'] for a in g['actions'] for s in a.get('subactions',[])}
        for page in pages:wanted[g['source']].add((g['program'],page))
    for reg in read(R/'movements/candidates.json')['registries']:
        for row in reg['evidence_rows']+reg['table_totals']:wanted[row['source']].add((row['program'],row['page']))
    for row in read(R/'reserves/candidates.json')['records']:
        for page in row['context_pages']:wanted[row['source']].add((row['program'],page))
    for row,proof in zip(read(D/'rap-explicit-zeros.json')['rows'],read(D/'rap-explicit-zeros.json')['proofs']):
        wanted[row['source']].add((row['program'],proof['page']))
    verified=[]
    for source in sources:
        path=Path(source['path'])
        with path.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==source['sha256']
        text=Path(source['text_path']).read_text(encoding='utf8');contexts=programme_context(text)
        cover_pages=set();proofs=[]
        with fitz.open(path) as pdf:
            for program,page in sorted(wanted[source['source']]):
                ctx=contexts[page]
                assert ctx['program']==program,(source['source'],page,program,ctx)
                opening=ctx['opening_page'];assert opening<=page<=len(pdf)
                if opening not in cover_pages:
                    physical=pdf[opening-1].get_text()
                    assert re.search(r'PROGRAMME\s+'+program+r'\b',physical),(source['source'],opening,program)
                    assert len(physical.strip())<800,(source['source'],opening,'not a programme cover')
                    cover_pages.add(opening)
                proofs.append(dict(program=program,page=page,programme_opening_page=opening))
        verified.append(dict(source=source['source'],sha256=source['sha256'],year=source['year'],mission=source['mission'],
                             programme_covers=len(cover_pages),page_checks=proofs))
    # Regression: cross-references in the narrative must never change ownership.
    fake='PROGRAMME 105\nAction extérieure\f'+('Commentaire long. '*60)+'\nprogramme 176\nSuite du commentaire\fTableau de réserve'
    assert programme_context(fake)[3]['program']=='105'
    programme_keys={(g['year'],g['mission'],g['program']) for g in read(R/'actions/candidates.json')['groups']}
    mov_keys={(r['scope']['years'][0],r['scope']['mission'],r['scope']['program']) for r in read(R/'movements/candidates.json')['registries']}
    res_keys={(r['year'],r['mission'],r['program']) for r in read(R/'reserves/candidates.json')['records']}
    coverage=dict(scope='Budget général, RAP 2023–2025 ; absence de tableau ne signifie pas montant nul.',
                  programme_years_with_action_tables=len(programme_keys),
                  without_movement_recap=[list(k) for k in sorted(programme_keys-mov_keys)],
                  without_reserve_table=[list(k) for k in sorted(programme_keys-res_keys)])
    report=dict(success=True,physical_pdfs_verified=len(verified),programme_covers_verified=sum(x['programme_covers'] for x in verified),
                page_programme_checks=sum(len(x['page_checks']) for x in verified),coverage=coverage,sources=verified)
    (R/'provenance-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sources','coverage')}|dict(
        programme_years_with_action_tables=len(programme_keys),without_movement_recap=len(programme_keys-mov_keys),without_reserve_table=len(programme_keys-res_keys))))

if __name__=='__main__':main()
