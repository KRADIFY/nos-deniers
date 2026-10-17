"""Source-bound complete partitions added to the existing selection hierarchy.

Canonical facts are retained. Native title/category rows are combined only when
a requested sub-action or fine exclusion requires their documented partition.
"""
import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

FILE=Path(__file__).parent/'data/internal-details-20261017.json'
KEY_FIELDS=('year','stage','measure','budget','mission','program','action')

def _encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def _path(row):
    return '/'.join(row[k] for k in ('mission','program','action','subaction') if row[k])

def _within(path,parent):
    return not parent or path==parent or path.startswith(parent+'/')

def _public(row):
    return {k:v for k,v in row.items() if not k.startswith('_')}

def _key(row):
    return tuple(row[k] for k in KEY_FIELDS)

def version_bytes():
    return FILE.read_bytes() if FILE.exists() else b''

@lru_cache(maxsize=1)
def registry():
    if not FILE.exists():return {}
    data=json.loads(FILE.read_bytes())
    assert data['schema']==1 and data['batch']=='coded-exact-20261017'
    result=defaultdict(list);seen=set()
    for part in data['partitions']:
        payload={k:v for k,v in part.items() if k!='partition_sha256'}
        assert hashlib.sha256(_encode(payload).encode()).hexdigest()==part['partition_sha256']
        key=tuple(part['key']);assert key not in seen;seen.add(key)
        assert part['complete'] and part['axis']=='official_coded_subactions'
        assert len({x['code'] for x in part['children']})==len(part['children'])
        assert sum(x['cents'] for x in part['children'])==part['parent_cents']
        result[key[:-1]].append(part)
    return result

def _walk(rows):
    for row in rows:
        yield row
        yield from _walk(row.get('_action_details',[]))

def _existing_child(rows,code,cents):
    matches=[r for r in rows if r['subaction']==code]
    if not matches or sum(r['cents'] for r in matches)!=cents:return None
    if len(matches)==1:return dict(matches[0])
    return dict(matches[0],cents=cents,title='',category='',
                _proof_rows=[_public(r) for r in matches])

def _children(part,parent,existing,published_row):
    group=dict(zip(KEY_FIELDS[:-1],part['key'][:-1]))
    group.update(source=part['source_dependencies'][0]['source'],
                 sha256=part['source_dependencies'][0]['sha256'],page=1)
    children=[]
    for item in part['children']:
        if item.get('preserve_existing'):
            child=_existing_child(existing,item['code'],item['cents'])
            if child is None:return None
        else:
            child=published_row(item,parent,group,'subaction')
            child.update(annual_label_variants=item['annual_label_variants'],
                         unit='EUR',unit_inferred=item['unit_inferred'],
                         printed_unit=item['printed_unit'],
                         source_evidence=item['source_evidence'])
            child['_detail_comparisons']=[dict(source=e['source'],page=e['page'])
                                         for e in item['source_evidence']]
        children.append(child)
    if sum(x['cents'] for x in children)!=part['parent_cents']:return None
    return children

def attach(records,db,published_row):
    groups=defaultdict(list)
    for row in records:groups[_key(row)[:-1]].append(row)
    source_checks={}
    for key,parts in registry().items():
        raw=groups.get(key)
        if not raw:continue
        for part in parts:
            fields=part['fact_guard_fields']
            signature=hashlib.sha256(_encode([{f:r.get(f) for f in fields} for r in raw]).encode()).hexdigest()
            if signature!=part['program_facts_sha256']:continue
            for dependency in part['source_dependencies']:
                pair=(dependency['source'],dependency['sha256'])
                if pair not in source_checks:
                    entry=db.execute('select data from sources where id=?',(pair[0],)).fetchone()
                    source_checks[pair]=bool(entry and json.loads(entry[0]).get('sha256')==pair[1])
            if not all(source_checks[(d['source'],d['sha256'])] for d in part['source_dependencies']):continue
            action=part['key'][-1]
            if part['kind']=='reviewed_registry_action':
                nodes=[n for r in raw for n in _walk(r.get('_action_details',[]))]
                parent=next((r for r in nodes if r['action']==action and not r['subaction']),None)
                if not parent or parent['cents']!=part['parent_cents'] or parent.get('_detail_review_required'):continue
                children=_children(part,parent,parent.get('_action_details',[]),published_row)
                if children is not None:parent['_action_details']=children
            elif part['kind']=='native_action_facts':
                parents=[r for r in raw if r['action']==action]
                if not parents or sum(r['cents'] for r in parents)!=part['parent_cents']:continue
                originals=[_public(r) for r in parents]
                virtual=dict(originals[0],subaction='',subaction_label='',title='',category='',
                             cents=part['parent_cents'],_proof_rows=originals)
                children=_children(part,virtual,parents,published_row)
                if children is None:continue
                virtual['_action_details']=children
                owner=parents[0]
                owner['_native_internal_children']=children
                owner['_native_internal_overlay']=dict(path=part['path'],virtual=virtual)
                for sibling in parents[1:]:sibling['_native_internal_owner']=part['path']
    return records

def resolve_native_parents(records,scope,excluded):
    records=list(records);active={}
    for row in records:
        overlay=row.get('_native_internal_overlay')
        if not overlay:continue
        path=overlay['path']
        if any(_within(path,e) for e in excluded) and (scope==path or not _within(scope,path)):continue
        if (scope!=path and _within(scope,path)) or any(e!=path and _within(e,path) for e in excluded):
            active[(_key(row)[:-1],path)]=overlay['virtual']
    for row in records:
        overlay=row.get('_native_internal_overlay');path=overlay['path'] if overlay else row.get('_native_internal_owner')
        if not path:
            yield row
            continue
        key=(_key(row)[:-1],path)
        if key not in active:yield row
        elif overlay:yield active[key]
