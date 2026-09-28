from pathlib import Path
p=Path('audit.py');s=p.read_text('utf-8');lines=s.splitlines(keepends=True)
for marker in ('from zeros import',"self.db.execute('create table if not exists zero_cases",'zero_source_summary='):
 seen=False;kept=[]
 for line in lines:
  if marker in line:
   if seen:continue
   seen=True
  kept.append(line)
 lines=kept
s=''.join(lines)
start=s.index('<h2>Zéros et cases sans montant</h2>');second=s.find('<h2>Zéros et cases sans montant</h2>',start+1)
if second>=0:s=s[:start]+s[second:]
p.write_text(s,'utf-8')
p=Path('zeros.py');s=p.read_text('utf-8')
for begin,end in [('        if column is None:\n','        if column is not None:'),("    with sqlite3.connect(out/'zeros-sources.sqlite') as db:",'    result=dict(structured_zero_facts=')]:
 start=s.index(begin);second=s.find(begin,start+len(begin));stop=s.index(end,start)
 if 0<=second<stop:s=s[:start]+s[second:]
p.write_text(s,'utf-8')
p=Path('Dockerfile');s=p.read_text('utf-8').replace('zeros.py zeros.py','zeros.py').replace('RUN pip install --no-cache-dir xlrd==2.0.2\nRUN pip install --no-cache-dir xlrd==2.0.2','RUN pip install --no-cache-dir xlrd==2.0.2');p.write_text(s,'utf-8')
