"""Read-only exact facts and citation lookup for a versioned Nos Deniers generation.

No aggregation or financial inference is performed. Documentary passages never
become certified figures through this reader.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3

DIMENSIONS = frozenset(('year','program','mission','action','subaction','stage','measure','budget','category','title'))


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def _child(root, relative):
    path = (root/str(relative)).resolve()
    if not path.is_relative_to(root) or path==root:
        raise ValueError('Path escapes generation')
    return path


def _ro(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    wal = Path(str(path)+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Generation has an active WAL; use a sealed snapshot')
    con = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    return con


def _catalogue(root):
    receipt_path = root/'numeric_addendum_receipt.json'
    if receipt_path.exists():
        receipt = _json(receipt_path)
        if receipt.get('passed') is not True:
            raise ValueError('Numeric integration is not complete')
        return _child(root,receipt['catalogue_relative_path'])
    choices = [root/name for name in ('catalogue.sqlite','nos_deniers.sqlite') if (root/name).is_file()]
    if len(choices)!=1:
        raise ValueError('Generation must identify exactly one catalogue')
    return choices[0]


def _table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",(name,)).fetchone() is not None


def _locator_lineage(locator):
    """Only parse published locator segments; never use SQL prefix matching.

    An unknown syntax can still resolve its exact evidence, but grants no guessed
    parent/page association. Page 3 and page 30 can therefore never collide.
    """
    lineage = [(locator,'exact')]
    match = re.fullmatch(r'page:([1-9]\d*)(?:/(?:table:([A-Za-z0-9][A-Za-z0-9_.-]*)|raw))?(?:/part:([1-9]\d*))?',locator)
    if not match:
        return lineage,None
    page = int(match.group(1))
    page_locator = 'page:'+str(page)
    if match.group(2):
        table_locator = page_locator+'/table:'+match.group(2)
        if table_locator!=locator:
            lineage.append((table_locator,'table'))
    if page_locator!=locator:
        lineage.append((page_locator,'page'))
    return lineage,page


def query_facts(generation_root, filters, limit=100, offset=0):
    """Paginated annual facts, in cents, preserving NULL and row-specific citations."""
    root = Path(generation_root).resolve()
    if not isinstance(filters,dict) or set(filters)-DIMENSIONS:
        raise ValueError('Only explicit annual-fact dimensions are allowed')
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
        raise ValueError('limit must be 1..1000 and offset a nonnegative integer')
    active_path = root/'structured/active_stores.json'
    active = _json(active_path)
    if active.get('numeric_addendum'):
        receipt = _json(_child(root,active['numeric_addendum']['receipt']))
        if receipt.get('passed') is not True or receipt.get('active_stores_sha256') != _sha(active_path):
            raise ValueError('Active stores do not match the completed integration receipt')
    store = active['budget']
    path = _child(root,store['path'])
    if _sha(path) != store['sha256']:
        raise ValueError('Active budget snapshot hash mismatch')
    db, catalogue = _ro(path), _ro(_catalogue(root))
    try:
        columns = [row[1] for row in db.execute('PRAGMA table_info(facts)')]
        if set(filters)-set(columns):
            raise ValueError('Requested dimension is absent from this facts schema')
        conditions, parameters = [], []
        for name,value in sorted(filters.items()):
            if value is None:
                conditions.append('"'+name+'" IS NULL')
                continue
            if name=='year':
                if type(value) is not int or not 1 <= value <= 9999:
                    raise ValueError('year must be an integer')
            else:
                if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{0,64}',value):
                    raise ValueError('Invalid dimension code: '+name)
                if name=='measure' and value not in ('AE','CP'):
                    raise ValueError('measure must be AE or CP')
            conditions.append('"'+name+'"=?')
            parameters.append(value)
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        total = db.execute('SELECT count(*) FROM facts'+where,parameters).fetchone()[0]
        # rowid breaks ties between identical observations without conflating them.
        order = [name for name in ('year','stage','measure','budget','mission','program','action','subaction','title','source','line','field') if name in columns]
        order_sql = ','.join('"'+name+'"' for name in order)+(',rowid' if order else 'rowid')
        rows = []
        for original in db.execute('SELECT rowid AS _observation_rowid,* FROM facts'+where+' ORDER BY '+order_sql+' LIMIT ? OFFSET ?',parameters+[limit,offset]):
            row = dict(original)
            source = catalogue.execute("SELECT asset_sha256,metadata_json FROM numeric_source_map WHERE store='budget' AND source_id=?",(row['source'],)).fetchone()
            if not source:
                raise ValueError('Missing provenance for numeric source '+str(row['source']))
            meta = json.loads(source['metadata_json'])
            cited_sha = meta.get('sha256') or meta.get('source_sha256')
            if cited_sha and cited_sha != source['asset_sha256']:
                raise ValueError('Conflicting source SHA in numeric provenance')
            row['citation'] = {'source_id':row['source'],'source_sha256':source['asset_sha256'],
                'url':meta.get('url'),'title':meta.get('title'),'line':row.get('line'),'field':row.get('field')}
            rows.append(row)
        returned = len(rows)
        return {'store':'budget','version_sha256':store['sha256'],'filters':dict(filters),
            'rows':rows,'total':total,'returned':returned,'limit':limit,'offset':offset,
            'next_offset':offset+returned if offset+returned<total else None,
            'truncated':offset>0 or returned<total,'has_more':offset+returned<total,
            'unit':'cents','currency':'EUR','source_ids':sorted({row['source'] for row in rows}),
            'aggregation_performed':False,'missing_is_zero':False,
            'scope':'Annual observations only; do not add hierarchy levels, sidecar registers or events.'}
    finally:
        db.close()
        catalogue.close()


def resolve_evidence(generation_root, passage_id):
    """Resolve an exact passage into every distinct occurrence/reference and proof.

    Optional metadata_json/page_proof_json/table_ref occurrence columns are passed
    through. Exact chunk, parsed table parent and parsed physical-page evidence are
    resolved separately, always within the same source SHA. Physical page reviews
    preserve their OCR/overlay provenance without inferring financial dimensions.
    """
    if not isinstance(passage_id,str) or not re.fullmatch(r'[0-9a-f]{64}',passage_id):
        raise ValueError('Expected an exact SHA-256 passage ID')
    root = Path(generation_root).resolve()
    db = _ro(_catalogue(root))
    reviews = None
    try:
        passage = db.execute('SELECT * FROM passages WHERE id=?',(passage_id,)).fetchone()
        if not passage:
            return None
        reviews_path = _child(root,'page_reviews.sqlite')
        if reviews_path.is_file():
            reviews = _ro(reviews_path)
        citations, proofs, table_refs = [], [], set()
        page_reviews, direct_references = {}, []
        quality_table = _table(db,'asset_quality')
        precedence_table = _table(db,'source_precedence')
        evidence_table = _table(db,'evidence')
        for occurrence in db.execute('SELECT * FROM occurrences WHERE passage_id=? ORDER BY id',(passage_id,)):
            occ = dict(occurrence)
            asset = occ['asset_sha256']
            q = db.execute('SELECT * FROM asset_quality WHERE asset_sha256=?',(asset,)).fetchone() if quality_table else None
            quality = dict(q) if q else {'table_layout':'not_certified','numeric_status':'raw_not_validated_facts'}
            quality['allow_automatic_numeric_fact'] = False
            superseded = db.execute('SELECT * FROM source_precedence WHERE old_sha256=?',(asset,)).fetchone() if precedence_table else None
            metadata = {}
            for name in ('metadata_json','page_proof_json'):
                if occ.get(name):
                    metadata[name.removesuffix('_json')] = json.loads(occ[name])
            if occ.get('table_ref'):
                table_refs.add(occ['table_ref'])
            lineage,page = _locator_lineage(occ['locator'])
            relationships = dict(lineage)
            local_proofs = []
            if evidence_table:
                placeholders = ','.join('?' for _ in lineage)
                for row in db.execute('SELECT * FROM evidence WHERE asset_sha256=? AND locator IN ('+placeholders+') ORDER BY locator,id',[asset]+[item[0] for item in lineage]):
                    proof = dict(row)
                    proof['relationship'] = relationships[proof['locator']]
                    if proof.get('summary_json'):
                        proof['summary'] = json.loads(proof.pop('summary_json'))
                        if proof['summary'].get('table_ref'):
                            table_refs.add(proof['summary']['table_ref'])
                        matched = [entry for entry in proof['summary'].get('chunk_references',[])
                                   if entry.get('passage_id')==passage_id and entry.get('occurrence_id')==occ['id']]
                        proof['direct_chunk_references'] = matched
                        for entry in matched:
                            if entry.get('table_ref'):
                                table_refs.add(entry['table_ref'])
                            direct_references.append({**entry,'source_sha256':asset,'page':page,
                                'proof_id':proof.get('id'),'relationship':'direct_chunk_reference',
                                'staged_document':proof['summary'].get('staged_document'),
                                'staged_document_sha256':proof['summary'].get('staged_document_sha256'),
                                'staged_record_no':proof['summary'].get('staged_record_no')})
                    proof['occurrence_id'] = occ['id']
                    local_proofs.append(proof)
                proofs.extend(local_proofs)
            review = None
            if reviews is not None and page is not None and _table(reviews,'page_reviews'):
                key = (asset,page)
                if key not in page_reviews:
                    stored = reviews.execute('SELECT * FROM page_reviews WHERE source_sha256=? AND page=?',key).fetchone()
                    if stored:
                        review = dict(stored)
                        if review.get('provenance_json'):
                            review['provenance'] = json.loads(review.pop('provenance_json'))
                        if _table(reviews,'page_review_evidence'):
                            evidence = reviews.execute('SELECT * FROM page_review_evidence WHERE source_sha256=? AND page=?',key).fetchone()
                            review['retained_evidence'] = dict(evidence) if evidence else None
                        review['relationship'] = 'physical_page_review'
                        page_reviews[key] = review
                review = page_reviews.get(key)
            refs = list(db.execute('SELECT * FROM refs WHERE asset_sha256=? ORDER BY id',(asset,)))
            if not refs:
                raise ValueError('Passage occurrence has no documentary reference')
            for ref in refs:
                meta = json.loads(ref['metadata_json'])
                citations.append({'occurrence_id':occ['id'],'reference_id':ref['id'],
                    'source_id':meta.get('id'),'source_sha256':asset,'title':meta.get('title'),'url':meta.get('url'),
                    'locator':occ['locator'],'section':occ.get('section'),'kind':occ.get('kind'),
                    'partition':ref['partition'],'documentary_years':meta.get('years',[]),
                    'documentary_stage':meta.get('stage_documentaire'),'quality':quality,
                    'superseded':dict(superseded) if superseded else None,
                    'occurrence_metadata':metadata,'table_ref':occ.get('table_ref'),
                    'physical_page':page,'page_review':review,
                    'proof_ids':[proof.get('id') for proof in local_proofs]})
        return {'passage':dict(passage),'citations':citations,'citation_count':len(citations),
            'proofs':proofs,'table_refs':sorted(table_refs),
            'direct_chunk_references':direct_references,'page_reviews':list(page_reviews.values()),
            'quality':{'numeric_status':'not_validated_budget_fact','allow_automatic_numeric_fact':False},
            'financial_dimensions_inferred':False,'aggregation_performed':False}
    finally:
        db.close()
        if reviews is not None:
            reviews.close()
