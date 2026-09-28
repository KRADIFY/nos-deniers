from pathlib import Path
p=Path('zeros.py');s=p.read_text('utf-8').replace('import collections,csv,hashlib,html,json,re,unicodedata','import collections,csv,hashlib,html,json,re,sqlite3,unicodedata')
s=s.replace("row=rows[line-1];headers=rows[0] if rows else [];wanted=[]","""row=rows[line-1];headers=rows[0] if rows else [];wanted=[]
        if column is None:
            # Some historical files begin with a GESTION/year row, before the header.
            candidates=[h for h in rows[:min(line-1,20)] if any(key(v)==key(field) for v in h)]
            signatures={tuple(key(v) for v in h) for h in candidates}
            if len(signatures)==1:headers=candidates[0]""")
s=s.replace("counts=dict(collections.Counter(i['status'] for i in items));out=Path(out)","""counts=dict(collections.Counter(i['status'] for i in items));out=Path(out)
    with sqlite3.connect(out/'zeros-sources.sqlite') as db:
        db.execute('create table if not exists items(status text, search text, data text)');db.execute('delete from items')
        db.executemany('insert into items values(?,?,?)',[(i['status'], ' '.join(str(i.get(k,'')) for k in ('budget','year','measure','stage','path','source_title','field')),json.dumps(i,ensure_ascii=False)) for i in items])
        db.execute('create index if not exists by_status on items(status)')""")
p.write_text(s,'utf-8')
p=Path('audit.py');s=p.read_text('utf-8')
s=s.replace('from management import Management','from management import Management\nfrom zeros import source_ledger,classify_cell,LABELS as ZERO_LABELS')
s=s.replace("('audit.py','oracle.py','management.py')","('audit.py','oracle.py','management.py','zeros.py')")
s=s.replace("self.done={r[0] for r in self.db.execute('select id from results')};self.changed=False","""self.db.execute('create table if not exists zero_cases(id text primary key,status text,search text,data text)')
        self.done={r[0] for r in self.db.execute('select id from results')};self.changed=False""")
s=s.replace("result['route']=route\n        return result","""result['route']=route
        zero_cells=[]
        for path,series in [(p['scope'],d['totals'])]+[(r['id'],r['series']) for r in d['rows']]:
            for annual in series:
                for stage in STAGES:
                    c=annual[stage];z=classify_cell(self.ref,p,annual['year'],stage,path,c)
                    if z:
                        selected={k:p[k] for k in ('budget','measure','exclude','constant','base','topic','topic_mode')}
                        item=dict(z,budget=p['budget'],measure=p['measure'],year=annual['year'],stage=stage,path=path,selection=selected)
                        identity=dump([selected,annual['year'],stage,path]);ident=hashlib.sha256(identity.encode()).hexdigest()
                        zero_cells.append((ident,z['status'],' '.join(str(item[k]) for k in ('budget','year','measure','stage','path')),dump(item)))
        with self.db:self.db.executemany('insert or replace into zero_cases values(?,?,?,?)',zero_cells)
        return result""")
s=s.replace("self.progress()\n        for i,(kind,p)","""self.progress()
        if 'zero-sources' not in self.done:
            try:
                summary=source_ledger(self.ref,os.environ.get('AUDIT_CORPUS_ROOT','/reference/data'),self.out)
                anomalies=sum(summary['counts'].get(k,0) for k in ('source_blank','source_dash','source_not_applicable','nonzero_source'))
                summary['errors']=[] if not anomalies else [dict(cell='Zéros enregistrés et contenu source',expected='Zéro ou calcul explicite',actual=str(anomalies)+' cas à relire dans le relevé des zéros.')]
                self.record('zero-sources','zero-sources',{},summary)
            except Exception as e:self.record('zero-sources','zero-sources',{},dict(errors=[dict(cell='Relecture des zéros',actual=str(e))],incomplete=True))
        for i,(kind,p)""")
s=s.replace("('browser','stability')])!=len(self.jobs)","('browser','stability','zero-sources')])!=len(self.jobs)")
s=s.replace("cases=len(rows),error_count=len(issues),issues=issues,documented_disagreements", "zero_source_summary=next((r['result'] for r in rows if r['kind']=='zero-sources'),{}),zero_case_counts=dict(self.db.execute('select status,count(*) from zero_cases group by status')),\n          cases=len(rows),error_count=len(issues),issues=issues,documented_disagreements")
s=s.replace('<h2>Anomalies</h2>', '<h2>Zéros et cases sans montant</h2><p>Une relecture dédiée distingue les zéros effectivement présents dans les cellules sources, les calculs nuls, les mentions documentaires et les sens non déterminés. Un blanc ou un tiret ne suffit jamais à prouver un zéro.</p><p><a href="zeros-sources.csv">Relevé des zéros sources · CSV</a> · <a href="zeros-sources.json">Détail des preuves · JSON</a></p><ul>{"".join("<li>"+esc(ZERO_LABELS.get(k,k))+" : "+str(v)+"</li>" for k,v in report["zero_source_summary"].get("counts",{}).items())}</ul><p>Ce relevé reste distinct de la conformité des montants restitués par le site. Une source non relue ne devient pas une preuve de zéro.</p><h2>Anomalies</h2>')
p.write_text(s,'utf-8')
p=Path('Dockerfile');s=p.read_text('utf-8').replace('WORKDIR /app','RUN pip install --no-cache-dir xlrd==2.0.2\nWORKDIR /app').replace('audit.py oracle.py management.py','audit.py oracle.py management.py zeros.py');p.write_text(s,'utf-8')
p=Path('.dockerignore');s=p.read_text('utf-8')+'\n!zeros.py\n';p.write_text(s,'utf-8')
p=Path('worker.py');s=p.read_text('utf-8')
s=s.replace("if not reference.exists():prepare(database,registries,reference)","""if reference.exists() and not (reference/'manifest.json').is_file():reference.rename(reference.with_name(reference.name+'.incomplete-'+str(time.time_ns())))
        if not reference.exists():prepare(database,registries,reference)""")
p.write_text(s,'utf-8')
