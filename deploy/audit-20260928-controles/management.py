"""Read the frozen management registries and check independent public API responses."""
from decimal import Decimal
from oracle import read,within

class Management:
    def __init__(self,ref):
        self.ref=ref;root=ref.folder/'registries'
        self.reserves={}
        for name in ('reserves-ecologie.json','reserves-national.json','reserves-historique-2017-2022.json'):
            for r in read(root/name).get('records',[]):
                key=(r['budget'],r['measure'],r['year'],r['mission']+'/'+r['program'])
                if key in self.reserves:
                    if name!='reserves-historique-2017-2022.json':raise ValueError('Réserve en double : '+str(key))
                    continue
                self.reserves[key]=r
        self.movements={};self.adjustments={};seen=set()
        regs=[read(root/'mouvements-rap-p174.json')]
        for name in ('mouvements-rap-national.json','mouvements-rap-historique-detail.json','mouvements-rap-autres-budgets-historique.json','mouvements-rap-historique.json'):
            regs.extend(read(root/name).get('registries',[]))
        for reg in regs:
            scope=reg['scope'];newyears={y for y in scope['years'] if (scope['budget'],scope['mission'],scope['program'],y) not in seen}
            for y in newyears:seen.add((scope['budget'],scope['mission'],scope['program'],y))
            for r in reg['items']:
                if r['year'] not in newyears:continue
                if r['id'] in self.movements:raise ValueError('Mouvement en double : '+r['id'])
                self.movements[r['id']]=r
            for r in reg.get('annual_adjustments',[]):
                if r['year'] in newyears:self.adjustments[r['id']]=r

    def reserves_check(self,p,data):
        errors=[];amounts=missing=0;seen=set()
        expected={k:r for k,r in self.reserves.items() if k[0]==p['budget'] and k[1]==p['measure'] and p['start']<=k[2]<=p['end'] and within(k[3],p['scope']) and not any(within(k[3],e) for e in p['exclude'])}
        for row in data.get('items',[]):
            key=(p['budget'],row['measure'],row['year'],row['path'])
            if not row['table_available']:
                if any(c.get('value') is not None for c in row['cells'].values()):errors.append(dict(cell=str(key),expected='table absente, sans valeur',actual=row['cells']))
                missing+=len(row['cells']);continue
            if key not in expected or key in seen:errors.append(dict(cell=str(key),expected='table unique de la référence',actual='table inattendue ou dupliquée'));continue
            seen.add(key);original=expected[key]
            for field in ('source','page','source_sha256'):
                if row.get(field)!=original.get(field):errors.append(dict(cell=str(key)+' '+field,expected=original.get(field),actual=row.get(field)))
            for field,c in row['cells'].items():
                o=original['cells'].get(field);wanted=o['total_cents'] if o else None
                if c.get('nominal_cents')!=wanted:errors.append(dict(cell=str(key)+' '+field,expected=wanted,actual=c.get('nominal_cents')))
                if c.get('source_cells')!=o:errors.append(dict(cell=str(key)+' '+field+' composantes',expected=o,actual=c.get('source_cells')))
                value=self.ref.converted(wanted,row['year'],p)
                if (value is None)!=(c.get('value') is None) or (value is not None and value!=Decimal(str(c['value']))):errors.append(dict(cell=str(key)+' '+field+' euros',expected=str(value),actual=c.get('value')))
                if wanted is None:missing+=1
                else:amounts+=1
        if seen!=set(expected):errors.append(dict(cell='réserves omises',expected=sorted(str(k) for k in set(expected)-seen),actual='absentes de l’API'))
        return dict(errors=errors,amounts=amounts,missing=missing,tables=len(seen))

    def movement_expected(self,p):
        return {k:r for k,r in self.movements.items() if r['budget']==p['budget'] and r['measure']==p['measure'] and p['start']<=r['year']<=p['end'] and within(r['mission']+'/'+r['program'],p['scope']) and not any(within(r['mission']+'/'+r['program'],e) for e in p['exclude'])}

    def movement_check(self,p,items):
        errors=[];amounts=missing=0;expected=self.movement_expected(p);seen=set()
        for r in items:
            key=r.get('id')
            if key not in expected or key in seen:errors.append(dict(cell=str(key),expected='mouvement unique connu',actual='inconnu ou doublon'));continue
            seen.add(key);original=expected[key]
            for field in ('year','budget','mission','program','measure','title','kind','date','date_precision','date_kind','sign','amount_cents','source','sha256','page'):
                if r.get(field)!=original.get(field):errors.append(dict(cell=key+' '+field,expected=original.get(field),actual=r.get(field)))
            wanted=None if original['amount_cents'] is None else original['sign']*original['amount_cents']
            if wanted!=r.get('nominal_cents'):errors.append(dict(cell=key+' montant signé',expected=wanted,actual=r.get('nominal_cents')))
            value=self.ref.converted(wanted,r['year'],p)
            if (value is None)!=(r.get('value') is None) or (value is not None and Decimal(str(r['value']))!=value):errors.append(dict(cell=key+' euros',expected=str(value),actual=r.get('value')))
            if not r.get('source_verified'):errors.append(dict(cell=key+' source',expected='empreinte confirmée',actual=False))
            if wanted is None:missing+=1
            else:amounts+=1
        if seen!=set(expected):errors.append(dict(cell='mouvements omis',expected=sorted(set(expected)-seen),actual='absents de l’API'))
        return dict(errors=errors,amounts=amounts,missing=missing,movement_rows=len(seen))
