"""Explanatory notices for 43 historical differences between publications.

These notes do not alter any fact, calculation, or chosen amount.
"""
import json
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
