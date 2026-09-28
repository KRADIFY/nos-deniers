import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.runtime/python-libs'))
import xlrd,openpyxl
OUT=ROOT/'reports/import-selenium-2019-2022-20260909'
SCAN=ROOT/'reports/selenium-budget/scan-2019-2022-cible-20260909/downloads'
plan=json.loads((OUT/'plan.json').read_text(encoding='utf-8'))
seen=set(); report=[]
for item in plan['items']:
    if item['sha256'] in seen:continue
    seen.add(item['sha256']);path=SCAN/item['filename']
    if path.suffix.lower() not in {'.xls','.xlsx'}:continue
    record={'filename':item['filename'],'sha256':item['sha256'],'valid':False}
    try:
        if path.suffix.lower()=='.xls':
            wb=xlrd.open_workbook(str(path),on_demand=True)
            record['sheets']=[{'name':s.name,'rows':s.nrows,'columns':s.ncols} for s in wb.sheets()]
            for s in wb.sheets():
                for row in range(s.nrows):s.row_values(row)
            wb.release_resources()
        else:
            wb=openpyxl.load_workbook(path,read_only=True,data_only=False)
            record['sheets']=[]
            for s in wb:
                rows=sum(1 for _ in s.iter_rows(values_only=True))
                record['sheets'].append({'name':s.title,'rows':rows})
            wb.close()
        record['valid']=True
    except Exception as e:record['error']=str(e)
    report.append(record)
    (OUT/'validation-workbooks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'workbooks':len(report),'valid':sum(r['valid'] for r in report),'errors':[r for r in report if not r['valid']]}))
if not all(r['valid'] for r in report):sys.exit(1)
