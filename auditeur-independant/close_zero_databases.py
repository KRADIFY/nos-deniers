from pathlib import Path
for name in ('zeros.py','zero_api.py','test_zero_api.py'):
 p=Path(name);s=p.read_text('utf-8');s='from contextlib import closing\n'+s
 if name=='zeros.py':s=s.replace("with sqlite3.connect(out/'zeros-sources.sqlite') as db:","with closing(sqlite3.connect(out/'zeros-sources.sqlite')) as db, db:")
 elif name=='zero_api.py':s=s.replace("with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as db:","with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:")
 else:s=s.replace("with sqlite3.connect(folder/'zeros-sources.sqlite') as db:","with closing(sqlite3.connect(folder/'zeros-sources.sqlite')) as db, db:")
 p.write_text(s,'utf-8')
