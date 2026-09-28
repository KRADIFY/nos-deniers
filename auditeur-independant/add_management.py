from pathlib import Path
p=Path(__file__).with_name('audit.py');s=p.read_text('utf8')
s=s.replace('from oracle import Reference,STAGES,compare_cells,digest,within', 'from oracle import Reference,STAGES,compare_cells,digest,within\nfrom management import Management')
s=s.replace("    return jobs\n", "    for b in ('BG','BA','CAS','CCF'):\n        for m in ('AE','CP'):\n            for constant in (False,True):\n                if quick and (b!='BG' or m!='CP' or constant):continue\n                jobs.append(('reserves',params(b,m,constant=constant)))\n                jobs.append(('movements',params(b,m,'TA/174' if quick else '',constant=constant)))\n    return jobs\n")
s=s.replace("self.a=a;self.ref=Reference(a.reference);self.client=Client(a.url,a.delay)", "self.a=a;self.ref=Reference(a.reference);self.management=Management(self.ref);self.client=Client(a.url,a.delay)")
s=s.replace("        route='/api/explorer?'+qs(p);d=self.client.get(route)", '''        if kind=='reserves':
            return self.management.reserves_check(p,self.client.get('/api/reserves?'+qs(p)))
        if kind=='movements':
            items=[];offset=0;visited=set();selection=None;total=None
            while True:
                d=self.client.get('/api/rap-movements?'+qs(p|dict(view='summary',limit=500,offset=offset)))
                if selection is None:selection=d['selection_id'];total=d['count']
                if d['selection_id']!=selection or d['count']!=total:raise ValueError('Mouvements modifiés pendant la pagination')
                items.extend(d['items'])
                if not d['has_more']:break
                nxt=d['next_offset']
                if not isinstance(nxt,int) or nxt<=offset or nxt in visited:raise ValueError('Pagination non progressive')
                visited.add(offset);offset=nxt
            if len(items)!=total:raise ValueError('Pagination incomplète : '+str((len(items),total)))
            return self.management.movement_check(p,items)
        route='/api/explorer?'+qs(p);d=self.client.get(route)''')
s=s.replace("'Tableaux dédiés des mouvements et réserves : pas encore de contrôle indépendant dans cette version.'", "'Actes juridiques de la chronologie et pièces justificatives détaillées des mouvements : non certifiés indépendamment.'")
s=s.replace("Le tableau des crédits, ses niveaux de détail et les scénarios annoncés sont contrôlés. Les autres pages ont leur couverture indiquée séparément.", "Tableau des crédits, niveaux de détail, montants des réserves et lignes de mouvements : comparaison à la référence. Les réconciliations documentaires ne sont pas refaites intégralement.")
p.write_text(s,'utf8');print('Contrôle des réserves et mouvements raccordé.')
