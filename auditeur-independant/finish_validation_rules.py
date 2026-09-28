from pathlib import Path
p=Path('audit.py');s=p.read_text('utf-8')
s=s.replace("for a in series:\n            for name,c in a.get('comparisons',{}).items():", """for a in series:
            if set(a.get('comparisons',{}))!={'LFI_PLF','EXEC_LFI','CONSUMPTION'}:errors.append(dict(cell=f'{path} {a["year"]} comparaisons attendues',actual=sorted(a.get('comparisons',{}))))
            if set(a.get('evolution',{}))!=set(STAGES):errors.append(dict(cell=f'{path} {a["year"]} étapes des variations',actual=sorted(a.get('evolution',{}))))
            for stage,rates in a.get('evolution',{}).items():
                if set(rates)!={'nominal_yoy','real_yoy','real_from_start'}:errors.append(dict(cell=f'{path} {a["year"]} {stage} variations attendues',actual=sorted(rates)))
            for name,c in a.get('comparisons',{}).items():""")
p.write_text(s,'utf-8')
p=Path('test_auditeur.py');s=p.read_text('utf-8').replace('parameters=p,years=', 'parameters=copy.deepcopy(p),years=');p.write_text(s,'utf-8')
p=Path('preview_service.py');s=p.read_text('utf-8').replace("AUDIT_NODE=str(Path.home()", "AUDIT_CORPUS_ROOT=str(Path('references/physical-sources').resolve()),\n AUDIT_NODE=str(Path.home()")
p.write_text(s,'utf-8')
