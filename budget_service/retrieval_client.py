"""Read-only bridge to the fixed private retrieval service and verified sources."""
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from .document_search import parameters


def configured():
    return bool(os.environ.get('BUDGET_RETRIEVAL_URL', '').strip())


def unavailable(message, state='unavailable'):
    return dict(available=False, state=state, items=[], count=0, message=message)


def request(path):
    endpoint = os.environ.get('BUDGET_RETRIEVAL_URL', '').rstrip('/')
    if not endpoint:
        return unavailable('La recherche sémantique n’est pas encore raccordée.', 'preparing')
    try:
        # Allow the retrieval engine's two-minute budget plus response delivery.
        with urlopen(endpoint + path, timeout=130) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError('Invalid retrieval response')
        return result
    except HTTPError as error:
        if error.code == 503:
            return unavailable('Le moteur est occupé ou momentanément indisponible. Relancez la recherche dans quelques instants.', 'busy')
        return unavailable('La recherche ou le passage demandé est indisponible.')
    except (URLError, TimeoutError, OSError, ValueError):
        return unavailable('Le moteur documentaire est momentanément indisponible. Réessayez dans quelques instants.')


def status():
    return request('/healthz')


def search(query):
    p = parameters(query)
    mode = query.get('mode', ['hybrid'])[0]
    if mode not in ('hybrid', 'text'):
        raise ValueError('Invalid search mode')
    return request('/search?' + urlencode({**{k: p[k] for k in ('q', 'year', 'format', 'limit')}, 'mode': mode}))


def passage(ident):
    if not re.fullmatch('[0-9a-f]{64}', ident):
        raise ValueError('Invalid passage')
    return request('/passage/' + ident)


def resolve_sources(result, db):
    """Resolve downloads by exact source hash, including topic PDFs outside SQL."""
    from . import api, topics
    topic_by_sha = {s['sha256']: s for s in topics.sources()}
    cache = {}
    recovered = {}

    def local_source(source, sha):
        if not source or source.get('sha256') != sha:
            return False
        if not re.fullmatch(r'[0-9a-f]{20}', source.get('id', '')):
            return False
        path = (api.DATA / source['path']).resolve()
        return path.is_relative_to(api.DATA.resolve()) and path.is_file()

    for item in result.get('items', []) + ([result] if 'citations' in result else []):
        for cite in item.get('citations', []):
            sha = cite.get('source_sha256')
            # Legacy full-text responses don't contain a source hash.
            if not sha:
                continue
            sid = cite.get('source_id', '')
            if sha in topic_by_sha:
                source = topic_by_sha[sha]
            else:
                if sid not in cache:
                    try:
                        cache[sid] = api.source(db, sid) if sid else None
                    except (ValueError, LookupError):
                        cache[sid] = None
                source = cache[sid]
            valid = local_source(source, sha)
            # Old indexes can predate the local registration of an original.
            # An exact source hash reconnects it without changing its vectors.
            if not valid and db is not None and re.fullmatch(r'[0-9a-f]{64}', sha):
                if sha not in recovered:
                    recovered[sha] = None
                    for row in db.execute("SELECT data FROM sources WHERE json_extract(data,'$.sha256')=? ORDER BY id", (sha,)):
                        candidate = json.loads(row[0])
                        if local_source(candidate, sha):
                            recovered[sha] = candidate
                            break
                source = recovered[sha]
                valid = source is not None
            cite['local_available'] = valid
            cite['source_id'] = source['id'] if valid else ''
    return result
