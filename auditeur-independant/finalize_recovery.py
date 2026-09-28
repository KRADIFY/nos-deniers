from pathlib import Path
p=Path('audit.py');s=p.read_text('utf-8').replace("self.done={r[0] for r in self.db.execute('select id from results')};self.changed=False", "self.done={i for i,r in self.db.execute('select id,result from results') if not json.loads(r).get('incomplete')};self.changed=False")
p.write_text(s,'utf-8')
p=Path('worker.py');s=p.read_text('utf-8').replace("state.update(status='complete',finished_unix=time.time(),message=result['verdict'])", "state.update(status='interrupted' if result['verdict']=='INCOMPLET' else 'complete',finished_unix=time.time(),message=result['verdict'])")
p.write_text(s,'utf-8')
p=Path('web/app.js');s=p.read_text('utf-8').replace("p.planned+2","p.planned+3");p.write_text(s,'utf-8')
p=Path('.dockerignore');s=p.read_text('utf-8').replace('!zeros.py\n\n!zeros.py','!zeros.py');p.write_text(s,'utf-8')
