from pathlib import Path
r=Path(__file__).resolve().parent
p=r/'oracle.py';s=p.read_text('utf8')
s=s.replace("roots=[p for p in self.leaves if p[:4]==key[:4] and within(p[-1],path)]", "roots=[] if not excluded else [p for p in self.leaves if p[:4]==key[:4] and within(p[-1],path)]")
s=s.replace("if len(path.split('/'))<=2 and roots:","if excluded and len(path.split('/'))<=2 and roots:")
s=s.replace("            else:\n                x,full=self.removed(key,excluded)","            elif excluded:\n                x,full=self.removed(key,excluded)")
p.write_text(s,'utf8')
p=r/'audit.py';s=p.read_text('utf8').replace("name=='real_since_start'","name=='real_from_start'")
s=s.replace("p.add_argument('--no-browser',action='store_true');", "p.add_argument('--resume-last',action='store_true');p.add_argument('--no-browser',action='store_true');")
s=s.replace("    a=p.parse_args()\n", "    a=p.parse_args()\n    if a.resume_last:\n        saved=json.loads((HERE/'dernier-scan.json').read_text('utf-8'))\n        for k,v in saved.items():setattr(a,k,Path(v) if k in ('reference','output') else v)\n")
s=s.replace("incomplete=any(r['result'].get('incomplete') for r in rows) or self.a.no_browser", "incomplete=any(r['result'].get('incomplete') for r in rows) or self.a.no_browser or len([r for r in rows if r['kind'] not in ('browser','stability')])!=len(self.jobs) or not any(r['kind']=='stability' for r in rows)")
p.write_text(s,'utf8')
print('Ajustements du lanceur et du calcul indépendant enregistrés.')
