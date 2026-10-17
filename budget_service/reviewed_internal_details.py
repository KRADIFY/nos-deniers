"""Annual internal devices, bound to reviewed facts, sources and relations.

The exact coded registry stays independent. A complete documentary list may
close a branch at its parent's published value only under its own signed
precision assessment. Partial lists never close an unexplained remainder.
"""
import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from .internal_details import KEY_FIELDS, _encode, _walk, _public

FILE=Path(__file__).parent/'data/internal-details-reviewed-20261017.json'

def version_bytes():
    return FILE.read_bytes() if FILE.exists() else b''

def _validate_node(node):
    assert isinstance(node['cents'],int)
    assert node['source'] and node['sha256'] and node['page']>0
    assert node['code_basis'] in ('local_navigation','official_action') and node['measure_binding']
    children=node.get('children',[])
    if not children:return
    assert len({c['code'] for c in children})==len(children)
    relation=node['relation'];difference=node['cents']-sum(c['cents'] for c in children)
    assert relation['parent_minus_children_cents']==difference
    assert relation['children_ids']==[c['audit_node_id'] for c in children]
    assert relation['parent_id']==node['audit_node_id']
    assert relation['status'] in ('partial','exact','published_precision')
    if relation['status']=='exact':assert difference==0
    if relation['status']=='published_precision':assert abs(difference)<=relation['bound_cents']
    for child in children:_validate_node(child)

@lru_cache(maxsize=1)
def registry():
    if not FILE.exists():return {}
    data=json.loads(FILE.read_bytes());assert data['schema']==1
    assert data['batch']=='p177-reviewed-20261017'
    result=defaultdict(list);seen=set()
    for part in data['partitions']:
        payload={k:v for k,v in part.items() if k!='partition_sha256'}
        assert hashlib.sha256(_encode(payload).encode()).hexdigest()==part['partition_sha256']
        key=tuple(part['key']);assert key not in seen;seen.add(key)
        assert part['axis']=='annual_purpose' and part['root']['cents']==part['parent_cents']
        _validate_node(part['root'])
        result[key[:-1]].append(part)
    return result

def _decorate(node,row,path,labels):
    row.update(budget_path=path,path_labels=labels,code_basis=node['code_basis'],
               annual_label=node['label'],printed_unit=node['printed_unit'],
               normalized_unit='EUR',unit_inferred=node['unit_inferred'],
               source_evidence=node['source_evidence'],printed_literal=node['literal'],
               measure_binding=node['measure_binding'],precision_quantum_cents=node['quantum_cents'])
    row['_reviewed_internal_node']=True
    row['_detail_comparisons']=[dict(source=e['source'],page=e['page']) for e in node['source_evidence']]
    if node.get('relation'):
        relation=node['relation'];row['internal_relation']=relation
        row['_partial_action_coverage']=relation['status']=='partial'
    else:
        row.pop('internal_relation',None)
    return row

def _children(node,parent,group,published_row):
    result=[]
    for child in node.get('children',[]):
        path=parent.get('budget_path') or '/'.join(parent[k] for k in ('mission','program','action','subaction') if parent[k])
        path+='/'+child['code']
        labels=dict(parent.get('path_labels',{}));labels[path]=child['label']
        item=dict(child,source_description=dict(precision=child['note'],document='PAP '+str(group['year']),column=group['measure']+' · '+child['label']))
        row=published_row(item,parent,group,'subaction')
        # Canonical columns still describe their original four levels. The full
        # navigation path carries the additional level without inventing a code.
        if parent.get('subaction'):
            row['subaction']=parent['subaction'];row['subaction_label']=parent['subaction_label']
        _decorate(child,row,path,labels)
        for key in ('_source_disagreement',):
            if key in parent:row[key]=parent[key]
        if child.get('children'):row['_action_details']=_children(child,row,group,published_row)
        result.append(row)
    return result

def attach(records,db,published_row):
    groups=defaultdict(list)
    for row in records:groups[tuple(row[k] for k in KEY_FIELDS[:-1])].append(row)
    for key,parts in registry().items():
        raw=groups.get(key)
        if not raw:continue
        for part in parts:
            guard=[{f:r.get(f) for f in part['fact_guard_fields']} for r in raw]
            if hashlib.sha256(_encode(guard).encode()).hexdigest()!=part['program_facts_sha256']:continue
            valid=True
            for dependency in part['source_dependencies']:
                source=db.execute('select data from sources where id=?',(dependency['source'],)).fetchone()
                if not source or json.loads(source[0]).get('sha256')!=dependency['sha256']:valid=False;break
            if not valid:continue
            action=part['key'][-1]
            parent=next((r for row in raw for r in _walk(row.get('_action_details',[]))
                         if r['action']==action and not r['subaction']),None)
            native=[]
            if part['kind']=='native_action_facts':
                native=[r for r in raw if r['action']==action]
                if not native or sum(r['cents'] for r in native)!=part['parent_cents']:continue
                originals=[_public(r) for r in native]
                parent=dict(originals[0],subaction='',subaction_label='',title='',category='',
                            cents=part['parent_cents'],_proof_rows=originals)
            if parent is None or parent['cents']!=part['parent_cents'] or parent.get('_action_details') or parent.get('_detail_review_required'):continue
            root=part['root'];path=part['path']
            labels={'/'.join(path.split('/')[:i+1]):parent[k] for i,k in enumerate(('mission_label','program_label','action_label'))}
            group=dict(zip(KEY_FIELDS[:-1],part['key'][:-1]));group.update(source=root['source'],sha256=root['sha256'],page=root['page'])
            _decorate(root,parent,path,labels)
            parent['_detail_note']=(parent.get('_detail_note','')+' '+root['note']).strip()
            parent['precision']=(parent.get('precision','')+' '+root['note']).strip()
            parent['_action_details']=_children(root,parent,group,published_row)
            if native:
                native[0]['_native_internal_children']=parent['_action_details']
                native[0]['_native_internal_overlay']=dict(path=path,virtual=parent)
                for sibling in native[1:]:sibling['_native_internal_owner']=path
    return records
