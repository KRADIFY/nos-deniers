"""Lossless table-to-text preparation, independent from storage and GPU execution.

Headers are source candidates, never inferred budget dimensions or certified facts.
The returned raw_table must accompany the chunks in the retrieval catalogue.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _value(value):
    if value is None:
        return '', 'null'
    if value == '' and isinstance(value, str):
        return '', 'empty_string'
    return (value if isinstance(value, str) else _json(value)), 'value'


def serialize_table(table, context, tokenizer, max_tokens=800):
    """Return raw_table, chunks and conservation evidence without side effects.

    table: {rows: [[value, ...], ...], header?: {names: [...]}, ...}.
    context requires source_id or source_sha256, a physical page, and table_id.
    tokenizer implements encode(text, add_special_tokens=True).ids, with truncation
    disabled. Coordinates, header candidates and all original values stay in raw_table.
    Each segment carries exact character offsets into its field; joining the segments
    reconstructs every original rendered value, including whitespace and Unicode.
    """
    if not isinstance(table, dict) or not isinstance(context, dict):
        raise TypeError('table and context must be dictionaries')
    rows = table.get('rows')
    if not isinstance(rows, list) or any(not isinstance(row, (list, tuple)) for row in rows):
        raise ValueError('rows must be a list of rows')
    if not context.get('source_id') and not context.get('source_sha256'):
        raise ValueError('A stable source identity is required')
    if not isinstance(context.get('page'), int) or isinstance(context['page'], bool) or context['page'] < 1:
        raise ValueError('A positive physical PDF page number is required')
    if context.get('table_id') is None or str(context['table_id']) == '':
        raise ValueError('An explicit table_id is required')
    if not isinstance(max_tokens, int) or max_tokens < 64 or max_tokens > 800:
        raise ValueError('max_tokens must be between 64 and 800')
    if getattr(tokenizer, 'truncation', None):
        raise ValueError('Tokenizer truncation must be disabled before serialization')

    def count(text):
        encoded = tokenizer.encode(text, add_special_tokens=True)
        ids = encoded.ids if hasattr(encoded, 'ids') else encoded
        return len(ids)

    original = {'table':deepcopy(table), 'context':deepcopy(context)}
    table_ref = hashlib.sha256(_json(original).encode('utf-8')).hexdigest()
    header = table.get('header') or {}
    names = header.get('names') or []
    if not isinstance(names, list):
        raise ValueError('header.names must be a list of unverified candidates')
    width = max((len(row) for row in rows), default=0)
    declared_width = table.get('column_count', width)
    if not isinstance(declared_width, int) or declared_width < width:
        raise ValueError('column_count cannot contradict the original rows')
    width = declared_width
    row_start = table.get('row_start', 1)
    if not isinstance(row_start, int) or row_start < 1:
        raise ValueError('row_start must be positive')

    # Full context and headers remain separate recoverable fields. Compact prefixes
    # reference those fields when repeating their full text would exceed the budget.
    metadata_fields, groups, expected = [], [], {}

    def field(ref, label, value, kind, **extra):
        text, state = _value(value)
        entry = {'field_ref':ref, 'label':label, 'text':text, 'state':state, 'kind':kind, **extra}
        expected[ref] = entry
        return entry

    for index, (key, value) in enumerate(context.items(), 1):
        metadata_fields.append(field('context:'+str(index), 'Contexte fourni '+str(index),
                                     _json({key:value}), 'context', context_key=key))
    for index, name in enumerate(names, 1):
        metadata_fields.append(field('header:'+str(index), 'En-tête candidat non certifié '+str(index),
                                     name, 'header_candidate', candidate_index=index))
    if metadata_fields:
        groups.append(metadata_fields)
    for index, row in enumerate(rows, row_start):
        row_fields = []
        for col in range(1, width+1):
            item = field('r'+str(index)+'c'+str(col), 'Ligne '+str(index)+' · Colonne '+str(col),
                         row[col-1] if col <= len(row) else None, 'cell', row=index, column=col)
            item['header_candidate_ref'] = 'header:'+str(col) if col <= len(names) else None
            item['header_assignment'] = 'positional_candidate_unverified'
            if col > len(row):
                item['state'] = 'not_present'
            row_fields.append(item)
        if row_fields:
            groups.append(row_fields)

    source = str(context.get('source_sha256') or context.get('source_id'))
    source_display = source if len(source) <= 80 else 'référence contexte '+table_ref[:16]
    title = str(context['table_id'])
    title_display = title if len(title) <= 60 else 'référence contexte '+table_ref[:16]
    base = (f'Source {source_display} · page {context["page"]} · tableau {title_display}\n'
            f'Référence complète {table_ref}\n'
            'En-têtes et contexte fournis, non certifiés. Aucun chiffre automatiquement validé.\n')
    if count(base+'\nLigne 1 · Colonne 1 [r1c1] : x') > max_tokens:
        raise ValueError('Source/table identity leaves insufficient token budget; no text was discarded')
    prefix = base
    prefix_budget = min(max_tokens-32, max_tokens//2)
    for entry in metadata_fields:
        # Reference keys are stable even when an oversized header is fragmented.
        addition = f'{entry["label"]} [{entry["field_ref"]}] : {entry["text"]}\n'
        if count(prefix+addition) <= prefix_budget:
            prefix += addition
    prefix += 'Contexte et en-têtes complets : champs context:* et header:* de la référence ci-dessus.\n\n'
    if count(prefix+'Ligne 1 · Colonne 1 [r1c1] : x') > max_tokens:
        raise ValueError('Metadata references exceed token budget; no text was discarded')

    chunks, pending = [], []
    placeholders = {'null':'[ABSENT : NULL]', 'empty_string':'[VIDE : chaîne vide]',
                    'not_present':'[ABSENT : colonne non présente dans cette ligne source]'}

    def segment(entry, start=0, end=None):
        end = len(entry['text']) if end is None else end
        return {key:value for key, value in entry.items() if key not in ('text',)} | {
            'text':entry['text'][start:end], 'char_start':start, 'char_end':end,
            'original_characters':len(entry['text']), 'complete':start == 0 and end == len(entry['text'])}

    def rendered(item):
        fragment = '' if item['complete'] else f' · caractères {item["char_start"]}:{item["char_end"]}'
        value = item['text'] if item['state'] == 'value' else placeholders[item['state']]
        return f'{item["label"]} [{item["field_ref"]}{fragment}] : {value}'

    def text_for(items):
        return prefix+'\n'.join(rendered(item) for item in items)

    def fits(items):
        return count(text_for(items)) <= max_tokens

    def flush():
        if not pending:
            return
        body = '\n'.join(rendered(item) for item in pending)
        text = prefix+body
        tokens = count(text)
        if not 0 < tokens <= max_tokens:
            raise ValueError('Serialized chunk exceeds its token contract')
        index = len(chunks)+1
        chunks.append({'text':text, 'body':body, 'tokens':tokens,
            'locator':f'page:{context["page"]}/table:{context["table_id"]}/part:{index}',
            'table_ref':table_ref, 'part':index, 'field_refs':[item['field_ref'] for item in pending],
            'segments':deepcopy(pending), 'quality':{
                'source_kind':'reconstructed_table', 'table_layout':'candidate_not_certified',
                'numeric_status':'raw_not_validated_facts', 'header_status':'source_candidates_not_certified',
                'allow_automatic_numeric_fact':False, 'raw_table_ref':table_ref}})
        pending.clear()

    def append_large_entry(entry):
        whole = segment(entry)
        if fits(pending+[whole]):
            pending.append(whole)
            return
        flush()
        if fits([whole]):
            pending.append(whole)
            return
        if not entry['text']:
            raise ValueError('An empty-cell marker cannot fit; no silent column removal')
        start = 0
        while start < len(entry['text']):
            low, high, best = start+1, len(entry['text']), None
            # Conservative character boundaries avoid token-offset overlap losses.
            # Every chosen prefix is counted including repeated identity and context.
            while low <= high:
                end = (low+high)//2
                candidate = segment(entry, start, end)
                if fits([candidate]):
                    best = candidate
                    low = end+1
                else:
                    high = end-1
            if best is None:
                raise ValueError('No lossless Unicode fragment fits the token budget')
            pending.append(best)
            flush()
            start = best['char_end']

    for group in groups:
        whole_group = [segment(entry) for entry in group]
        if fits(whole_group):
            if not fits(pending+whole_group):
                flush()
            pending.extend(whole_group)
        else:
            # Only oversized rows fall back to cell-level or character fragments.
            flush()
            for entry in group:
                append_large_entry(entry)
    flush()

    seen = {}
    for chunk in chunks:
        for item in chunk['segments']:
            prior = seen.setdefault(item['field_ref'], {'text':'', 'end':0, 'count':0})
            if item['char_start'] != prior['end']:
                raise ValueError('Gap or overlap in field fragments')
            prior['text'] += item['text']
            prior['end'] = item['char_end']
            prior['count'] += 1
    if set(seen) != set(expected):
        raise ValueError('Missing source field')
    for ref, entry in expected.items():
        if seen[ref]['text'] != entry['text'] or (not entry['text'] and seen[ref]['count'] != 1):
            raise ValueError('Lossless conservation check failed: '+ref)
    return {'raw_table':{'schema':'nos-deniers-table-text-v1', 'table_ref':table_ref,
                        **original, 'column_count':width,
                        'header_policy':'All supplied header names remain unverified candidates; no inferred year/stage/AE/CP.'},
            'chunks':chunks, 'contract':{'max_tokens':max_tokens, 'truncate':False,
                'chunk_count':len(chunks), 'field_count':len(expected),
                'source_text_conserved':True, 'source_characters':sum(len(x['text']) for x in expected.values()),
                'allow_automatic_numeric_fact':False, 'requires_raw_table_for_provenance':True}}
