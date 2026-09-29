"""Assemble the 2026-09-29 historical-data and auditor-only update."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'auditeur-independant'
STAGED=ROOT/'reports/historical-76-20260929'
OUT=ROOT/'deploy/historique-76-20260929'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def copy(source,name):
    dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,dest)
    return name


def main():
    receipt=json.loads((STAGED/'receipt.json').read_text('utf-8'))
    db=STAGED/'data/derived/budget.sqlite'
    assert sha(db)==receipt['database_sha256']
    names=[copy(db,'data/budget.sqlite')]
    for filename in ('coverage.py','zeros.py','zero_reconcile.py','worker.py'):
        names.append(copy(SOURCE/filename,'audit/'+filename))
    names.append(copy(SOURCE/'web/zeros.js','audit/zeros.js'))
    for filename in ('test_coverage.py','test_zeros.py','test_zero_reconcile.py'):
        names.append(copy(SOURCE/filename,'tests/'+filename))
    release=dict(tag='20260929-historique76',data_version=receipt['data_version'],
                 baseline_sha256=receipt['base_sha256'],database_sha256=receipt['database_sha256'],
                 fact_count=receipt['fact_count'],review_count=receipt['review_count'],
                 integrated_management_cells=32,former_programme_cells_explained=44,
                 web_image_preserved='lexmachine-budget:20260929-consultation-chaude',
                 auditor_image_predecessor='nos-deniers-audit:20260929-arret',
                 indexed_vectors_changed=False,visual_presentation_changed=False)
    (OUT/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),'utf-8')
    names+=['Dockerfile','.dockerignore','install.py','PUBLIER_SUR_VPS.sh','release.json']
    manifest={name:sha(OUT/name) for name in names}
    (OUT/'FILES.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(folder=str(OUT),files=len(manifest),bytes=sum((OUT/name).stat().st_size for name in names),database_sha256=receipt['database_sha256']),ensure_ascii=False))

if __name__=='__main__':main()
