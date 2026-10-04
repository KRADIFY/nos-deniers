"""Explanatory notices for 43 historical differences between publications.

These notes do not alter any fact, calculation, or chosen amount.
"""
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

_REGISTRY = Path(__file__).with_name('data') / 'historical_discrepancy_notices_2017_2022.json'


@lru_cache(maxsize=1)
def _by_key():
    entries = json.loads(_REGISTRY.read_text(encoding='utf-8'))['entries']
    return {(r['year'], r['budget'], r['mission'], r['program'], r['measure'], r['stage']): r
            for r in entries}


def matching(parameters, year, stage, scope, result):
    """Attach only to the unchanged, complete programme amount in current euros."""
    parts = scope.split('/') if scope else []
    if len(parts) != 2 or parameters.get('topic'):
        return None
    key = (year, parameters['budget'], parts[0], parts[1], parameters['measure'], stage)
    entry = _by_key().get(key)
    if not entry:
        return None
    for excluded in parameters.get('exclude', []):
        if excluded == scope or excluded.startswith(scope + '/') or scope.startswith(excluded + '/'):
            return None
    if result.get('nominal_cents') != entry['site_cents']:
        return None
    return entry


def included(values, parameters, year, stage):
    """Notices whose unchanged programme amount contributes to this total."""
    if parameters.get('topic') or not parameters.get('budget') or not parameters.get('measure'):
        return []
    programme_amounts = defaultdict(int)
    for row in values:
        programme_amounts[(row['mission'], row['program'])] += row['cents']
    notices = []
    for (mission, program), amount in sorted(programme_amounts.items()):
        scope = f'{mission}/{program}'
        selected = parameters.get('scope', '')
        if selected and selected != scope and not scope.startswith(selected + '/'):
            continue
        if any(excluded == scope or excluded.startswith(scope + '/') or scope.startswith(excluded + '/')
               for excluded in parameters.get('exclude', [])):
            continue
        entry = _by_key().get((year, parameters['budget'], mission, program,
                               parameters['measure'], stage))
        if entry and amount == entry['site_cents']:
            notices.append(entry)
    return notices
