"""Reviewed cell evidence, kept distinct from amounts and from missing values."""
import json
from collections import defaultdict

class Records(list):
    def __init__(self, rows, reviews):
        super().__init__(rows)
        self.cell_reviews = reviews

class IndexedReviews(dict):
    """Preserve review order while indexing the group looked up by each cell."""
    def __init__(self, rows):
        super().__init__(rows)
        self.by_cell = defaultdict(list)
        for (year, stage, measure, budget, path), review in self.items():
            self.by_cell[(year, stage, measure, budget)].append((path, review))


def load(db):
    if not db.execute("select 1 from sqlite_master where name='cell_reviews' and type='table'").fetchone():
        return {}
    return IndexedReviews(((r['year'],r['stage'],r['measure'],r['budget'],r['path']),json.loads(r['data']))
                          for r in db.execute('select * from cell_reviews'))


def matching(reviews, p, year, stage, scope):
    if not reviews: return []
    key=(year,stage,p['measure'],p['budget'])
    candidates=(reviews.by_cell.get(key, ()) if isinstance(reviews,IndexedReviews)
                else ((path,r) for (y,s,m,b,path),r in reviews.items() if (y,s,m,b)==key))
    return [r for path,r in candidates
            if (not scope or path==scope or path.startswith(scope+'/'))
            and not any(path==e or path.startswith(e+'/') for e in p['exclude'])]


def citations(rows):
    found={}
    for row in rows:
        for p in row['proofs']:
            key=(p['source_id'],p['physical_page'])
            found[key]=dict(source=key[0],page=key[1],label=p['evidence'])
    return list(found.values())

def explain(rows, result, prior, scope=None):
    if not rows: return prior
    exact = len(rows)==1 and (scope is None or rows[0]['path']==scope)
    if not prior:
        prior=dict(status=result['status'],title='Source et périmètre du montant',summary='',details=[],
                   references=[],contacts=[],request_text='',known_components=[],contextual_amounts=[])
    prior['checked_at']='2026-09-28'
    if exact:
        r=rows[0]
        prior['summary']=r['explanation']
        prior['details']=[r['method']]
        if r['status']=='not_applicable':
            prior.update(title='Pourquoi cette case est non applicable ?',contacts=[],request_text='')
        elif r['status']=='pending':
            prior['title']='Montant restant à confirmer'
        else:
            prior['title']='Montant contrôlé dans les documents sources'
    else:
        prior['details'].extend(f"{r['path']} : {r['explanation']} {r['method']}" for r in rows)
    prior['references'].extend(citations(rows))
    return prior
