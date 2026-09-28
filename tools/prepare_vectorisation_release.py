"""Unpaid local controller for the corrected Nos Deniers vectorisation bundle.

Wait for the other task's completed OCR receipt, stage PDF pages, work on ONE
private catalogue copy, integrate numerical stores, export, then audit the closed
generation. The active preparation and its previous export are never replaced.
No RunPod/API transfer, encoder or deployment exists in this controller.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from prepare_vectorisation_tables import (ROOT, PREPARATION, SOURCE_CODE, STAGE,
    atomic_json, canonical, file_hash, read_db, stage)

GENERATION_STORAGE = Path('F:/LexMachine/NosDeniers')
GENERATION = GENERATION_STORAGE/'generation_tables_20260911'
REMEDIATION = SOURCE_CODE/'QUALITY_REMEDIATION_20260911.json'


def progress(root, phase, **details):
    data = {'at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'phase':phase,
            'gpu_launched':False,'paid_compute_authorized':False, **details}
    atomic_json(Path(root)/'controller_status.json',data)
    print(canonical(data),flush=True)


def check_space(path, minimum_gib):
    free = shutil.disk_usage(path).free
    if free < minimum_gib*1024**3:
        raise ValueError(f'Insufficient free disk space: {free/1024**3:.1f} GiB; required {minimum_gib}')


def freeze_runtime(root):
    names = ['prepare_vectorisation_release.py','prepare_vectorisation_tables.py',
             'vectorisation_table_geometry.py','vectorisation_table_text.py',
             'vectorisation_page_replacement.py','integrate_vectorisation_tables.py',
             'vectorisation_numeric_integration.py','vectorisation_release_contract.py',
             'query_vectorisation_generation.py','vectorisation_cour_contract.py']
    copies = root/'runtime'
    copies.mkdir(exist_ok=True)
    files = {}
    for name in names:
        source = Path(__file__).parent/name
        sha = file_hash(source)
        target = copies/name
        if target.exists() and file_hash(target) != sha:
            raise ValueError('Code changed since this generation started: '+name)
        if not target.exists():
            shutil.copyfile(source,target)
        files[name] = {'source':str(source),'path':str(target),'sha256':sha}
    atomic_json(root/'runtime_manifest.json',files)
    return files


def verify_runtime(files):
    for name,item in files.items():
        if file_hash(item['source']) != item['sha256'] or file_hash(item['path']) != item['sha256']:
            raise ValueError('Code changed during the generation: '+name)


def await_ocr(root, wait_for_receipt):
    while True:
        if REMEDIATION.exists():
            receipt = json.loads(REMEDIATION.read_text(encoding='utf-8'))
            if receipt.get('pdf_quality_repair_complete'):
                snapshot = Path(receipt['snapshot']['snapshot'])
                if not snapshot.is_file():
                    raise ValueError('Final OCR snapshot is unavailable')
                if file_hash(snapshot) != receipt['snapshot']['sha256']:
                    raise ValueError('Final OCR snapshot SHA differs')
                atomic_json(Path(root)/'source_ocr_receipt.json',receipt)
                return snapshot, receipt
        progress(root,'waiting_for_other_task_ocr_receipt',receipt=str(REMEDIATION))
        if not wait_for_receipt:
            raise ValueError('The other task has not yet frozen its corrected PDF snapshot')
        time.sleep(45)


def copy_catalogue(snapshot, root, expected_sha):
    target = root/'catalogue.sqlite'
    receipt_path = root/'catalogue_copy_receipt.json'
    if target.exists():
        if not receipt_path.exists():
            raise ValueError('Catalogue exists without its copy receipt; preserve and inspect it')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt['source_sha256'] != expected_sha:
            raise ValueError('Generation uses another baseline; preserve this generation')
        return target
    check_space(root, 48)
    progress(root,'copying_private_catalogue',source=str(snapshot),bytes=snapshot.stat().st_size)
    temporary = target.with_suffix('.partial')
    shutil.copyfile(snapshot,temporary)
    if file_hash(temporary) != expected_sha:
        raise ValueError('Private catalogue copy differs from the frozen baseline')
    temporary.replace(target)
    atomic_json(receipt_path,{'source':str(snapshot),'source_sha256':expected_sha,
                             'destination':str(target),'source_unchanged':True})
    return target


def rebuild_search(catalogue,root):
    con = sqlite3.connect(catalogue)
    try:
        progress(root,'verifying_private_search_index')
        state = con.execute("SELECT 1 FROM sqlite_master WHERE name='vectorisation_index_state'").fetchone()
        if state and not con.execute("SELECT 1 FROM vectorisation_index_state WHERE name='passages_fts' AND dirty<>0").fetchone():
            expected = con.execute('SELECT count(*) FROM passages').fetchone()[0]
            actual = con.execute('SELECT count(*) FROM passages_fts').fetchone()[0]
            if expected != actual:
                raise ValueError('Integrated search index count differs')
            atomic_json(root/'search_index_receipt.json',{'passages':expected,'fts_rows':actual,'passed':True,'rebuilt_by_table_integrator':True})
            return
        # Build once for the whole batch. Per-passage deletes on an UNINDEXED FTS
        # identity column would scan millions of rows for every corrected chunk.
        con.execute('BEGIN IMMEDIATE')
        con.execute('DROP TABLE IF EXISTS passages_fts')
        con.execute("CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,text,tokenize='unicode61 remove_diacritics 2')")
        con.execute('INSERT INTO passages_fts SELECT id,text FROM passages')
        con.execute("INSERT OR REPLACE INTO metadata VALUES('vectorisation_fts_dirty','0')")
        con.commit()
        expected = con.execute('SELECT count(*) FROM passages').fetchone()[0]
        actual = con.execute('SELECT count(*) FROM passages_fts').fetchone()[0]
        if expected != actual:
            raise ValueError('Search index count differs from catalogue')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        atomic_json(root/'search_index_receipt.json',{'passages':expected,'fts_rows':actual,'passed':True})
    finally:
        con.close()


def export_input(catalogue, root, config):
    sys.path.insert(0,str(SOURCE_CODE))
    from complement import quality_payload, verify_propagation
    from vectorisation_page_replacement import export_passage_ids
    export = root/'gpu_input'
    export.mkdir(exist_ok=True)
    target = export/'public.bge-m3.jsonl'
    contract_path = export/'contract.json'
    if target.exists() and contract_path.exists():
        old = json.loads(contract_path.read_text(encoding='utf-8'))
        if file_hash(target) == old['input_sha256']:
            return target, old
        raise ValueError('Previously exported generation input changed')
    con = read_db(catalogue)
    temporary = target.with_suffix('.partial')
    count = tokens = 0
    try:
        quality = verify_propagation(con)
        with temporary.open('w',encoding='utf-8',newline='\n') as stream:
            for passage_id in export_passage_ids(con):
                row = con.execute('SELECT id,text,tokens FROM passages WHERE id=?',(passage_id,)).fetchone()
                item = dict(row)
                item['quality'] = quality_payload(con,passage_id)
                item['quality']['page_review_catalogue'] = 'page_reviews.sqlite'
                item['quality']['numeric_calculations'] = 'structured/active_stores.json only'
                item['quality']['semantic_search_allowed'] = True
                item['quality']['source_quotation_allowed'] = True
                item['quality']['dimension_verification_required_before_aggregation'] = True
                stream.write(canonical(item)+'\n')
                count += 1
                tokens += row['tokens']
                if count % 10000 == 0:
                    progress(root,'exporting_corrected_input',passages=count,tokens=tokens)
                    check_space(root,4)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        con.close()
    contract = {'input':target.name,'input_sha256':file_hash(target),'input_count':count,
                'tokens':tokens,'model':config['model'],'revision':config['model_revision'],
                'dimension':config['dense_dimension'],'max_tokens':config['max_tokens_including_context'],
                'dense_normalized':config['dense_normalized'],'dense_dtype':config['dense_dtype'],
                'sparse_dtype':config['sparse_dtype'],'colbert':config['colbert'],'truncate':False,
                'paid_compute_authorized':False,'quality_propagation':quality,
                'gate':'Only the final generation manifest can validate the input; paid launch requires separate authorization.'}
    atomic_json(contract_path,contract)
    return target,contract


def notify_result(root, subject, body):
    """Use the user's existing DPAPI-backed notifier; never expose credentials."""
    receipt = Path(root)/('notification-'+file_hash_text(subject+body)+'.json')
    if receipt.exists():
        return
    try:
        result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',
            str(SOURCE_CODE/'notify.ps1'),'-Subject',subject,'-Body',body],capture_output=True,text=True,timeout=45)
    except (OSError,subprocess.TimeoutExpired):
        atomic_json(Path(root)/'notification_error.json',{'delivered':False,
                    'reason':'Notifier unavailable or timed out; preparation state is preserved.'})
        return
    if result.returncode != 0 or 'Email sent.' not in result.stdout:
        atomic_json(Path(root)/'notification_error.json',{'delivered':False,'exit_code':result.returncode,
                    'reason':'Existing notifier failed; credentials are intentionally omitted.'})
        return
    atomic_json(receipt,{'delivered':True,'subject':subject,'at':time.time()})


def file_hash_text(text):
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def run(root=GENERATION,stage_root=STAGE,workers=4,wait_for_receipt=False,notify=False):
    from integrate_vectorisation_tables import integrate_stage, generation_lock
    from vectorisation_numeric_integration import integrate_numeric_addendum
    from vectorisation_release_contract import build_release_manifest
    root,stage_root = Path(root).resolve(),Path(stage_root).resolve()
    allowed_roots = (PREPARATION.resolve(),GENERATION_STORAGE.resolve())
    if not any(root.is_relative_to(base) and root != base for base in allowed_roots):
        raise ValueError('The private generation must remain inside an explicitly named Nos Deniers storage folder')
    root.mkdir(parents=True,exist_ok=True)
    with generation_lock(root/'controller.lock'):
        if (root/'frozen/manifest.json').exists():
            frozen = json.loads((root/'frozen/manifest.json').read_text(encoding='utf-8'))
            if frozen.get('semantic_encoding_ready') is not True:
                raise ValueError('Existing manifest does not attest semantic readiness')
            for key in ('input','catalogue','page_review_db'):
                item = frozen['files'][key]
                if file_hash(item['path']) != item['sha256']:
                    raise ValueError('Previously frozen artifact changed: '+key)
            # Finish the handoff even after a crash between manifest publication
            # and the small user-facing receipt; never redo the large catalogue.
            if not (root/'HANDOFF.json').exists():
                atomic_json(root/'HANDOFF.json',{'generation_root':str(root),
                    'manifest':str(root/'frozen/manifest.json'),
                    'input':frozen['files']['input']['path'],
                    'catalogue':frozen['files']['catalogue']['path'],
                    'page_reviews':frozen['files']['page_review_db']['path'],
                    'replaces_for_next_encoding':str(PREPARATION/'gpu_input/public.bge-m3.jsonl'),
                    'original_export_deleted':False,'launch_authorized':False,
                    'note':'Recovered handoff after manifest publication. Do not mix generations.'})
            progress(root,'already_frozen',manifest=str(root/'frozen/manifest.json'))
            return
        try:
            snapshot,ocr = await_ocr(root,wait_for_receipt)
            runtime = freeze_runtime(root)
            progress(root,'staging_pdf_pages',snapshot=str(snapshot),workers=workers)
            staged = stage(snapshot,PREPARATION,stage_root,workers)
            if not staged['complete'] or staged['documents_expected'] != 4402 or staged['pages'] != 322172:
                raise ValueError('Full PDF staging is incomplete; inspect staging status before further processing')
            catalogue = copy_catalogue(snapshot,root,ocr['snapshot']['sha256'])
            verify_runtime(runtime)
            progress(root,'integrating_pages_on_private_copy')
            integrated = integrate_stage(generation_root=root,catalogue=catalogue,
                                         stage_root=stage_root,source_extracted_root=PREPARATION/'extracted')
            atomic_json(root/'table_integration_receipt.json',integrated)
            progress(root,'integrating_numeric_addendum')
            numeric = integrate_numeric_addendum(catalogue,root,
                         ROOT/'reports/audit-vectorisation-20260911/numeric-addendum',PREPARATION)
            atomic_json(root/'numeric_integration_summary.json',numeric)
            verify_runtime(runtime)
            rebuild_search(catalogue,root)
            baseline_config = json.loads((stage_root/'staging_contract.json').read_text(encoding='utf-8'))['config']
            atomic_json(root/'encoding_config.json',baseline_config)
            input_path,encoding_contract = export_input(catalogue,root,baseline_config)
            progress(root,'checking_closed_generation',input_count=encoding_contract['input_count'])
            stores = json.loads((root/'structured/active_stores.json').read_text(encoding='utf-8'))
            numeric_stores = {name:str(root/value['path']) for name,value in stores.items()
                              if isinstance(value,dict) and value.get('path','').endswith('.sqlite')}
            con = read_db(catalogue)
            try:
                registries = {r['registry_key']:str(root/r['relative_path']) for r in con.execute('SELECT * FROM numeric_registry_versions')}
            finally:
                con.close()
            manifest_config = {'catalogue':str(catalogue),'input':str(input_path),
                'baseline_config':str(root/'encoding_config.json'),'baseline_contract':str(PREPARATION/'gpu_input/contract.json'),
                'page_review_db':integrated['page_review_db'],'extracted_root':str(PREPARATION/'extracted'),
                'expected_pdf_pages':322172,'expected_grid_alert_pages':94764,
                'active_stores':numeric_stores,'registries':registries,
                'artifact_groups':{'sources':[str(root/'source_ocr_receipt.json'),str(root/'catalogue_copy_receipt.json')],
                    'provenance':[str(root/'table_integration_receipt.json'),str(root/'numeric_addendum_receipt.json')],
                    'corrections':[str(stage_root/'receipts.json'),str(stage_root/'staging_contract.json'),str(root/'runtime_manifest.json'),
                                   str(root/'search_index_receipt.json')]}}
            atomic_json(root/'manifest_config.json',manifest_config)
            verify_runtime(runtime)
            manifest = build_release_manifest(manifest_config,root/'frozen')
            progress(root,'generation_verified',manifest=str(root/'frozen/manifest.json'),
                     original_export_retained=True,public_site_modified=False,
                     numeric_automation_ready=False,
                     structured_budget_facts=120576,semantic_search_allowed=True,
                     cour_connection='See separate Cour audit; external passages remain accessible in the local catalogue.')
            atomic_json(root/'HANDOFF.json',{'generation_root':str(root),'manifest':str(root/'frozen/manifest.json'),
                'input':str(input_path),'catalogue':str(catalogue),'page_reviews':integrated['page_review_db'],
                'replaces_for_next_encoding':str(PREPARATION/'gpu_input/public.bge-m3.jsonl'),
                'original_export_deleted':False,'launch_authorized':False,
                'note':'Do not mix passage IDs from the old and corrected exports. Use this generation as one bound set.'})
            if notify:
                notify_result(root,'Nos Deniers — préparation contrôlée terminée',
                    f'La nouvelle génération a passé ses contrôles locaux. Dossier : {root}\n'
                    f'PDF : 4402 ; pages : 322172 ; passages préparés : {encoding_contract["input_count"]}.\n'
                    'Les références et limites de chaque page sont conservées ; cela ne certifie pas automatiquement les chiffres budgétaires.\n'
                    'Les accès Cour des comptes restent décrits dans leur audit séparé.\n'
                    'Aucun GPU lancé, aucun transfert RunPod ni dépense engagée. Les anciens exports sont conservés.\n'
                    'Le fichier HANDOFF.json indique le lot corrigé à utiliser pour la prochaine vectorisation.')
        except BaseException as exc:
            progress(root,'stopped_requires_review',error=type(exc).__name__+': '+str(exc),
                     prior_sources_and_exports_preserved=True)
            if notify:
                notify_result(root,'Nos Deniers — préparation à contrôler',
                    f'Le traitement local s’est arrêté avec ses points de reprise préservés. Dossier : {root}\n'
                    f'Cause : {type(exc).__name__}: {exc}\n'
                    'Aucun GPU ni dépense RunPod. Les sources et anciens exports restent conservés.\n'
                    'Le lot ne doit pas être envoyé à la vectorisation tant que le contrôle final n’est pas validé.')
            raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation',type=Path,default=GENERATION)
    parser.add_argument('--stage',type=Path,default=STAGE)
    parser.add_argument('--workers',type=int,default=4,choices=range(1,5))
    parser.add_argument('--wait-for-ocr',action='store_true')
    parser.add_argument('--notify',action='store_true')
    args=parser.parse_args()
    run(args.generation,args.stage,args.workers,args.wait_for_ocr,args.notify)
