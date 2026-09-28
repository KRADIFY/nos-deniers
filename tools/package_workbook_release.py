import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'reports/integration-classeurs-20260928'
OUT=ROOT/'deploy/update-20260928-classeurs'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def copy(src,rel):
    dest=OUT/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((WORK/'receipt.json').read_text('utf-8'))
    for name in ('api.py','cell_reviews.py'):copy(ROOT/'budget_service'/name,'app/budget_service/'+name)
    for name in ('explorer.html','assets/explorer.css','assets/explorer.js'):copy(ROOT/'public'/name,'app/public/'+name)
    copy(ROOT/'tests/test_workbook_cell_reviews.py','app/tests/test_workbook_cell_reviews.py')
    copy(ROOT/'tools/install_workbook_release.py','install.py')
    copy(ROOT/'tools/workbook_release_verify.py','verify.py')
    copy(WORK/'plan.json','plan.json')
    copy(WORK/'data/derived/budget.sqlite','data/derived/budget.sqlite')
    plan=json.loads((WORK/'plan.json').read_text('utf-8'))
    data_files=['derived/budget.sqlite']
    for record in plan['new_sources']:
        copy(WORK/'data'/record['path'],'data/'+record['path']);data_files.append(record['path'])
    for name in ('verification.json','independent-oracle.json','browser.json','unit-tests.log'):
        copy(WORK/name,'checks/'+name)
    (OUT/'Dockerfile').write_text('ARG BASE\nFROM ${BASE}\nCOPY app/ /app/\n','utf-8')
    (OUT/'PUBLIER_SUR_VPS.sh').write_text('#!/bin/sh\nset -eu\ncd /home/marie/nos-deniers-update-20260928-classeurs\nexec sudo python3 ./install.py "$@"\n','utf-8')
    contract=dict(release='20260928-classeurs',data_version=receipt['data_version'],database_sha256=receipt['database_sha256'],
                  baseline_sha256=receipt['baseline_sha256'],fact_count=123483,data_files=data_files,
                  files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in ('release.json','TRANSFER-VERIFIED.json')})
    (OUT/'release.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(folder=str(OUT),files=len(contract['files']),bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),data_version=receipt['data_version'])))
if __name__=='__main__':main()
