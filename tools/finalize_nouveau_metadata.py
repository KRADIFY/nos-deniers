import json,re,unicodedata,collections
from pathlib import Path
R=Path(__file__).resolve().parents[1]/'reports/import-nouveau-dossier-20260909'
def read(n):return json.loads((R/n).read_text(encoding='utf-8'))
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if not unicodedata.combining(c))
v=read('validation.json');p=read('plan.json');m=read('manifest-merged.json'); changes=[]
months='janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre'.split()
for x in v['files']:
    old=(x['year'],x['stage']); t=norm(x['head_text'])
    if x['stage'] not in ('rap','recueil_comptabilite'):
        assert 'situation' in t and ('budget' in t or 'mensuelle' in t),x['filename']
        x['stage']='situation_mensuelle'
        match=re.search(r'\bau\s+\d{1,2}\s+('+'|'.join(months)+r')\s+(20(?:1[7-9]|2[0-6]))',t)
        if match:x['year']=match[2];x['month']=months.index(match[1])+1
        else: print('DATE_REVIEW',x['filename'],x['year'])
    if old!=(x['year'],x['stage']):changes.append([x['filename'],old,(x['year'],x['stage'])])
    oldpath=x['path'];x['path']=re.sub(r'/document/', '/'+x['stage']+'/',oldpath)
    for r in p['new_records']+m:
        if r.get('sha256')==x['sha256']:
            r.update(path=x['path'],years_title=[x['year']],document_stage=x['stage'])
            if 'month' in x:r['document_month']=x['month']
    for r in p['items']:
        if r['sha256']==x['sha256']:r['path']=x['path']
p['summary']['new_years']=dict(collections.Counter(x['year'] for x in v['files']))
p['summary']['new_stages']=dict(collections.Counter(x['stage'] for x in v['files']))
v['summary']=p['summary']
for n,data in [('plan.json',p),('validation.json',v),('manifest-merged.json',m)]:
    (R/n).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(changes,ensure_ascii=False));print(json.dumps(p['summary']))
