"""Candidats de tableaux PDF par géométrie ; aucun fait financier automatique.

Le module ne lit ni n'écrit de base. L'appelant garde le PDF, les mots positionnés
et l'ancien shard jusqu'à validation d'une nouvelle génération de préparation.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import unicodedata

METHOD = 'native_cluster_closed_outer_edges_v1'


def tokens(text):
    return Counter(re.findall(r'\w+', unicodedata.normalize('NFC', str(text)).casefold()))


def word_center_inside(word, box, tolerance=1):
    x, y = (word[0] + word[2]) / 2, (word[1] + word[3]) / 2
    return box[0] - tolerance <= x <= box[2] + tolerance and box[1] - tolerance <= y <= box[3] + tolerance


def coverage_for_words(source_words, rows):
    source = sum((tokens(word[4]) for word in source_words), Counter())
    rendered = sum((tokens(cell) for row in rows for cell in row if cell is not None), Counter())
    missing = source - rendered
    total = sum(source.values())
    return {'source_tokens': total, 'covered_tokens': total - sum(missing.values()),
            'ratio': (total - sum(missing.values())) / total if total else 0,
            'missing_tokens': dict(missing),
            'missing_numeric_tokens': {token: count for token, count in missing.items() if any(c.isdigit() for c in token)},
            'complete': bool(total) and not missing,
            'scope': 'Couverture des mots/chiffres ; ne certifie pas la lecture métier des cellules.'}


def combined_credit_headers(names):
    result = []
    for index, name in enumerate(names):
        text = unicodedata.normalize('NFC', str(name or '')).casefold()
        ae = bool(re.search(r'\bae\b|autorisations?', text))
        cp = bool(re.search(r'\bcp\b|paiements?', text))
        if ae and cp:
            result.append(index + 1)
    return result


def meaningful_grid(rows):
    numeric_rows = sum(any(re.search(r'\d', str(cell)) for cell in row if cell is not None) for row in rows[1:])
    nonempty_columns = {i for row in rows for i, cell in enumerate(row) if cell is not None and str(cell).strip()}
    dated_columns = sum(bool(re.search(r'\b(?:19|20)\d{2}\b', str(cell))) for cell in (rows[0] if rows else []))
    single_indicator = len(rows) >= 2 and len(nonempty_columns) >= 4 and numeric_rows >= 1 and dated_columns >= 2
    # Presentation panels with a title/year are not sufficient evidence of a table.
    return {'rows': len(rows), 'columns': max((len(row) for row in rows), default=0),
            'nonempty_columns': len(nonempty_columns), 'numeric_body_rows': numeric_rows,
            'plausible': (len(rows) >= 3 and len(nonempty_columns) >= 3 and numeric_rows >= 2) or single_indicator}


def header_geometry(words, box, rows, row_cell_boxes, header):
    top_cells = [cell for row in row_cell_boxes[:3] for cell in row if cell]
    end = max((cell[3] for cell in top_cells), default=box[1] + 65)
    end = min(end, box[1] + 100, box[3])
    candidates = [word for word in words if box[0] - 1 <= (word[0] + word[2]) / 2 <= box[2] + 1
                  and box[1] - 85 <= (word[1] + word[3]) / 2 <= end]
    return {'status': 'candidates_not_certified', 'source_words': candidates,
            'first_rows': rows[:3], 'first_row_cell_boxes': row_cell_boxes[:3],
            'detected_header': header,
            'note': 'Conserver les groupes Prévision/Consommation/cumulée et AE/CP avec leurs positions ; aucune propagation automatique des années.'}


def recovery_candidates(page, record=None):
    """Return accepted candidates plus explicit rejected candidates and raw fallback.

    A candidate with complete lexical coverage remains a structural candidate,
    never a validated numeric fact. No whole-page text-grid inference is used.
    """
    import fitz
    source_words = record.get('words', []) if record is not None else [list(word) for word in page.get_text('words', sort=True)]
    source_blocks = record.get('blocks', []) if record is not None else [
        {'bbox': list(block[:4]), 'text': block[4]} for block in page.get_text('blocks', sort=True)
        if len(block) > 6 and block[6] == 0]
    physical_page = record.get('page') if record is not None else page.number + 1
    result = {'tables': [], 'rejected_candidates': [], 'diagnostics': [],
              'physical_page': physical_page, 'method': METHOD, 'automatic_numeric_fact': False,
              'fallback': {'status': 'raw_positioned_words_preserved', 'words': source_words, 'blocks': source_blocks}}
    if record is not None and str(record.get('method', '')).startswith('ocr'):
        result['diagnostics'].append('OCR : reconstruction native non appliquée ; contrôle des coordonnées OCR nécessaire.')
        return result
    try:
        drawings = page.get_drawings()
        regions = page.cluster_drawings(drawings=drawings)
    except Exception as exc:
        result['diagnostics'].append('Clustering impossible : ' + type(exc).__name__ + ': ' + str(exc))
        return result
    seen = set()
    for region_index, region in enumerate(regions, 1):
        region = fitz.Rect(region)
        if region.width < 80 or region.height < 20:
            continue
        if not any(word_center_inside(word, region) for word in source_words):
            continue
        edges = [(region.tl, region.tr), (region.tr, region.br),
                 (region.br, region.bl), (region.bl, region.tl)]
        clip = fitz.Rect(region.x0 - 1, region.y0 - 1, region.x1 + 1, region.y1 + 1) & page.rect
        try:
            finder = page.find_tables(strategy='lines', clip=clip, paths=drawings, add_lines=edges)
            # Serialize immediately: a following find_tables call replaces shared state.
            serialized = []
            for table in finder.tables:
                serialized.append({'bbox': list(table.bbox), 'rows': table.extract(),
                                   'cells': [list(cell) if cell else None for cell in table.cells],
                                   'row_cell_boxes': [[list(cell) if cell else None for cell in row.cells] for row in table.rows],
                                   'header': {'names': table.header.names, 'external': table.header.external,
                                              'bbox': list(table.header.bbox)}})
        except Exception as exc:
            result['diagnostics'].append(f'Région {region_index} : ' + type(exc).__name__ + ': ' + str(exc))
            continue
        for table in serialized:
            identity = hashlib.sha256(json.dumps({'bbox': table['bbox'], 'rows': table['rows']},
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if identity in seen:
                continue
            seen.add(identity)
            box = table['bbox']
            inside_words = [word for word in source_words if word_center_inside(word, box)]
            coverage = coverage_for_words(inside_words, table['rows'])
            shape = meaningful_grid(table['rows'])
            combined = combined_credit_headers(table['header']['names'])
            before = [block for block in source_blocks if block['bbox'][3] >= box[1] - 100
                      and block['bbox'][3] <= box[1] + 1 and block['bbox'][2] >= box[0] and block['bbox'][0] <= box[2]]
            reasons = []
            if not coverage['complete']:
                reasons.append('Mots ou chiffres sources absents des cellules reconstruites')
            if not shape['plausible']:
                reasons.append('Géométrie insuffisante pour distinguer un tableau chiffré de la mise en page')
            if combined:
                reasons.append('AE et CP restent réunis dans un même en-tête de colonne')
            table.update({'id': identity, 'physical_page': physical_page, 'method': METHOD,
                          'region_bbox': list(region), 'synthetic_edges': [[list(a), list(b)] for a, b in edges],
                          'source_word_count': len(inside_words), 'source_words': inside_words,
                          'context_before': before, 'coverage': coverage, 'grid': shape,
                          'combined_ae_cp_columns': combined, 'numeric_status': 'raw_not_validated_facts',
                          'allow_automatic_numeric_fact': False, 'replacement_allowed': not reasons,
                          'review_status': 'structural_candidate_only', 'rejection_reasons': reasons})
            table['header_geometry'] = header_geometry(source_words, box, table['rows'], table['row_cell_boxes'], table['header'])
            (result['rejected_candidates'] if reasons else result['tables']).append(table)
    if not result['tables']:
        result['diagnostics'].append('Structure non résolue : conserver les blocs et mots positionnés ; aucune substitution automatique.')
    return result
