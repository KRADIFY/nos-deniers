from contextlib import closing
import json,re,sqlite3
from urllib.parse import parse_qs

def query(state,query_string):
    p=parse_qs(query_string);rid=p.get('run',[''])[0];kind=p.get('kind',['sources'])[0]
    if not re.fullmatch(r'\d{8}-\d{6}-[a-f0-9]{6}',rid) or kind not in ('sources','cases'):raise ValueError('Sélection invalide')
    page=int(p.get('page',['0'])[0]);status=p.get('status',[''])[0];search=p.get('q',[''])[0]
    if page<0 or page>100000 or len(search)>200 or len(status)>60:raise ValueError('Filtre invalide')
    folder=state/'runs'/rid;path=folder/('zeros-sources.sqlite' if kind=='sources' else 'checkpoints.sqlite')
    if not path.is_file():return dict(items=[],count=0,counts={},message='Le relevé est en préparation.',page=page)
    table='items' if kind=='sources' else 'zero_cases'
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        if not db.execute('select 1 from sqlite_master where type="table" and name=?',(table,)).fetchone():return dict(items=[],count=0,counts={},message='Le relevé est en préparation.',page=page)
        clauses=[];args=[]
        if status:clauses.append('status=?');args.append(status)
        for term in search.split():
            clauses.append("search like ? escape '\\'");args.append('%'+term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        where=' where '+' and '.join(clauses) if clauses else ''
        total=db.execute('select count(*) from '+table+where,args).fetchone()[0]
        counts=dict(db.execute('select status,count(*) from '+table+' group by status'))
        rows=db.execute('select data from '+table+where+' order by rowid limit 60 offset ?',args+[page*60]).fetchall()
    return dict(items=[json.loads(r[0]) for r in rows],count=total,counts=counts,page=page,has_more=(page+1)*60<total)
