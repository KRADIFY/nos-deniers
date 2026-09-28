from oracle import Reference,read
from audit import plan
from pathlib import Path
r=Reference(Path('references/20260924-final'))
key=('BG','CP',2021,'EXEC','TA/345/09')
for p in ['TA/345','TA/345/09']+sorted(r.children[('BG','CP','TA/345/09')]):
 k=key[:-1]+(p,)
 print(k,r.amounts.get(k),'leaf',k in r.leaves,'blocked',k in r.blocked)
print('GROUP',*[g for g in r.groups if (g['year'],g['program'],g['measure'],g['stage'])==(2021,'345','CP','EXEC')])
print('jobs',len(plan(r)))
