"""Read-only retrieval audit through the user's existing private client. No AI generation."""
import importlib.util
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/audit-20260909/recherche-bases-existantes'
OUT.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('existing_private_client', ROOT.parent / 'BRAINSTORMING_R23/private_corpus_api/client.py')
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)
CASES = [
    ('cour-comptes', 'budget État 2025 réserve précaution gel dégel crédits MaPrimeRénov'),
    ('jorf', 'Décret 2024-124 portant annulation de crédits'),
    ('circulaires', 'réserve de précaution crédits budgétaires gel dégel programmation'),
    ('plf-pli', 'projet loi finances 2026 crédits mission écologie'),
    ('AN', 'MaPrimeRénov crédits budget 2025'),
    ('Senat', 'MaPrimeRénov crédits budget 2025'),
    ('questions-ecrites', 'MaPrimeRénov crédits gel annulation'),
    ('legislation', 'loi organique lois finances crédits reports réserve'),
    ('dossiers-legislatifs', 'loi finances 2026 crédits'),
    ('propositions-loi', 'rénovation énergétique financement budget'),
    ('jurisprudence', 'crédits budgétaires annulation réserve précaution'),
    ('kali', 'rénovation énergétique financement public'),
    ('cnil', 'MaPrimeRénov Anah'),
]
def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

summary = {'started_at': datetime.now(timezone.utc).isoformat(), 'scope': 'targeted retrieval witnesses across each exposed source; not an exhaustive absence proof', 'ai_generation': False, 'items': []}
with client_module.PrivateClient(port=0) as client:
    write(OUT / 'capabilities.json', client.request('/capabilities'))
    for source, query in CASES:
        result_path = OUT / (source + '.json')
        receipt_path = OUT / (source + '-receipt.json')
        item = {'source': source, 'query': query, 'mode': 'optimal', 'top_k': 12}
        started = time.monotonic()
        try:
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding='utf-8'))
            else:
                if receipt_path.exists():
                    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                else:
                    receipt = client.request('/jobs', {'source': source, 'query': query, 'mode': 'optimal', 'top_k': 12}, key='nos-deniers-audit-20260909-' + source)
                    write(receipt_path, receipt)
                job_id = receipt.get('job_id') or receipt.get('id')
                if not job_id:
                    raise RuntimeError('missing_job_id:' + json.dumps(receipt,ensure_ascii=False)[:300])
                while True:
                    result = client.request('/jobs/' + job_id)
                    state = result.get('status')
                    if state in ('completed','complete','done','failed','error','cancelled'):
                        write(result_path, result)
                        break
                    if time.monotonic() - started > 240:
                        item['pending_job_id'] = job_id
                        item['status'] = 'still_running_no_resubmission'
                        summary['items'].append(item)
                        write(OUT / 'summary.json',summary)
                        print(json.dumps(item,ensure_ascii=False),flush=True)
                        sys.exit(0)
                    time.sleep(2)
            item['status'] = result.get('status')
            payload = result.get('result',result)
            if isinstance(payload,dict):
                rows = payload.get('hits',payload.get('results',payload.get('items',[])))
                item['count'] = len(rows) if isinstance(rows,list) else None
                item['result_keys'] = list(payload)
            item['result_path'] = str(result_path)
        except Exception as error:
            item['status']='error'
            item['error_type']=type(error).__name__
            item['message']=str(error)[:400]
        item['elapsed_seconds']=round(time.monotonic()-started,2)
        summary['items'].append(item)
        write(OUT / 'summary.json',summary)
        print(json.dumps(item,ensure_ascii=False),flush=True)
        if item['status']=='error':
            break
summary['finished_at']=datetime.now(timezone.utc).isoformat()
write(OUT / 'summary.json',summary)
