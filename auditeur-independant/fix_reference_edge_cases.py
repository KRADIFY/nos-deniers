from pathlib import Path
p=Path(__file__).with_name('oracle.py');s=p.read_text('utf8')
s=s.replace("if any(not any(within(e,c[-1]) for c in children) for e in finer):return None,False", "if key in self.leaves and any(not any(within(e,c[-1]) for c in children) for e in finer):return None,False")
s=s.replace("            if year<2020 or params['budget']!='BG':return amount", "            if year<2020 or params['budget']!='BG':return amount\n            carriers=[c['path'] for c in self.mpr['carriers'] if (within(c['path'],path) or within(path,c['path'])) and not any(within(c['path'],e) or within(path,e) for e in excluded)]\n            if not carriers:return amount")
p.write_text(s,'utf8')
# Active audit script remains untouched until the current development run ends.
print('Cas des nomenclatures successives et des autres missions corrigés dans le contrôleur.')
