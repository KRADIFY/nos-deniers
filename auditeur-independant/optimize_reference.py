from pathlib import Path
p=Path(__file__).with_name('oracle.py');s=p.read_text('utf8')
s=s.replace("self.warnings=[];self.leaves=set()", "self.warnings=[];self.leaves=set();self.roots_by_bucket=collections.defaultdict(set)")
s=s.replace("self.group_rows[(b,m,y,s,r['mission']+'/'+r['program'])].append(r)", "self.group_rows[(b,m,y,s,r['mission']+'/'+r['program'])].append(r)\n            self.roots_by_bucket[(b,m,y,s)].add(r['mission']+'/'+r['program'])")
s=s.replace("roots=[] if not excluded else [p for p in self.leaves if p[:4]==key[:4] and within(p[-1],path)]", "roots=[] if not excluded else [key[:4]+(p,) for p in self.roots_by_bucket[key[:4]] if within(p,path)]")
p.write_text(s,'utf8');print('Index des périmètres préparé.')
