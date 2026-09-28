import argparse,html,json,os,sys,time,traceback
from pathlib import Path
from audit import Campaign,save
from prepare_reference import prepare
from oracle import digest
from coverage import run as documentary_check
from mutation_check import run as mutation_check
from reporting import write_outputs

ROOT=Path(__file__).resolve().parent
STATE=Path(os.environ.get('AUDIT_STATE_DIR','/audit-data'))

def main():
    rid=sys.argv[1];out=STATE/'runs'/rid;state=json.loads((STATE/'service-state.json').read_text('utf-8'))
    try:
        database=Path(os.environ.get('AUDIT_DATABASE','/reference/data/derived/budget.sqlite'))
        registries=Path(os.environ.get('AUDIT_REGISTRIES','/reference/registries'))
        audited_files=('audit.py','oracle.py','management.py','zeros.py','document_zeros.py','document-zero-proofs.json','reporting.py','coverage.py','coverage_report.py','document-coverage.json','mutation_check.py','browser.cjs','worker.py')
        code_signature={n:digest(ROOT/n) for n in audited_files}
        snapshot=digest(database)
        registry_id=__import__('hashlib').sha256(''.join(digest(p) for p in sorted(registries.glob('*.json'))).encode()).hexdigest()
        reference=STATE/'references'/(snapshot[:20]+'-'+registry_id[:20])
        if reference.exists() and not (reference/'manifest.json').is_file():reference.rename(reference.with_name(reference.name+'.incomplete-'+str(time.time_ns())))
        if reference.exists() and not (reference/'manifest.json').is_file():reference.rename(reference.with_name(reference.name+'.incomplete-'+str(time.time_ns())))
        if not reference.exists():prepare(database,registries,reference)
        if digest(database)!=snapshot:raise ValueError('Base modifiée pendant la lecture. Relancer le contrôle.')
        a=argparse.Namespace(reference=reference,output=out,url=os.environ.get('AUDIT_TARGET_URL','https://budget.lexmachine.net'),
          delay=float(os.environ.get('AUDIT_REQUEST_DELAY','0.15')),quick=os.environ.get('AUDIT_QUICK_FOR_TEST')=='1',
          no_browser=False,node=Path(os.environ.get('AUDIT_NODE','/usr/bin/node')))
        result=Campaign(a).run()
        coverage_dir=out/'coverage'
        coverage=documentary_check(reference,[os.environ.get('AUDIT_CORPUS_ROOT','/reference/data')],coverage_dir)
        result['document_coverage']={k:v for k,v in coverage.items() if k not in ('labels','parse_issues')}
        result['document_coverage']['reading_issues']=len(coverage['parse_issues'])
        if coverage['counts'].get('matched',0):
            mutations=mutation_check(reference,coverage_dir,coverage_dir/'mutations.json')
            result['mutation_tests']={k:v for k,v in mutations.items() if k!='results'}
            if not mutations['passed']:raise ValueError('Le moteur ne détecte pas toutes les erreurs injectées : aucun feu vert.')
        else:result['mutation_tests']={'passed':False,'status':'non exécutés faute de cellule témoin documentaire'}
        if {n:digest(ROOT/n) for n in audited_files}!=code_signature:raise ValueError('Code du contrôle modifié pendant la campagne.')
        current_registry_id=__import__('hashlib').sha256(''.join(digest(p) for p in sorted(registries.glob('*.json'))).encode()).hexdigest()
        if current_registry_id!=registry_id:raise ValueError('Registres modifiés pendant la campagne.')
        result['checked_release']=dict(database_sha256=snapshot,registry_signature=registry_id,auditor_code=code_signature,site_assets=result['identity']['assets'],global_documentary_certificate=False)
        save(out/'rapport.json',result);write_outputs(out,result,a.url)
        if digest(database)!=snapshot:raise ValueError('La base en ligne a changé pendant le contrôle : nouveau scan nécessaire.')
        state.update(status='interrupted' if result['verdict']=='INCOMPLET' else 'complete',finished_unix=time.time(),message=result['verdict']);save(STATE/'service-state.json',state)
        return 0 if result['passed'] else 2
    except BaseException as e:
        if (out/'rapport.json').exists():
            report=json.loads((out/'rapport.json').read_text('utf-8'));report.update(passed=False,verdict='INCOMPLET');save(out/'rapport.json',report)
        (out/'rapport.html').write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Contrôle incomplet</title><h1>Contrôle incomplet</h1><p>'+html.escape(str(e))+'</p><p>Aucun certificat de conformité émis. Les points de reprise sont conservés.</p></html>','utf-8')
        save(out/'ECHEC.json',dict(error=str(e),traceback=traceback.format_exc()))
        state.update(status='interrupted' if isinstance(e,KeyboardInterrupt) else 'error',message='Contrôle incomplet : '+str(e));save(STATE/'service-state.json',state)
        print(traceback.format_exc(),flush=True);return 2
if __name__=='__main__':sys.exit(main())
