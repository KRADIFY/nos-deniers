import json,sqlite3,sys,collections
from pathlib import Path
folder=Path(sys.argv[1]);c=sqlite3.connect(folder/'checkpoints.sqlite')
print(c.execute('select kind,status,count(*) from results group by kind,status').fetchall())
for kind,params,result in c.execute("select kind,params,result from results where status='erreur'"):
 r=json.loads(result);print(kind,params,'ERRORS',len(r.get('errors',[])));print(json.dumps(r.get('errors',[])[:4],ensure_ascii=False))
