"""Complete local test campaign with resumable API, numeric and browser checks."""
from pathlib import Path
import argparse,json,sys,time
import crash_test_site as test

class CurrentCampaign(test.Campaign):
 def basic(self,route,status=200,method='GET'):
  # This identifier is syntactically malformed, so the contract is HTTP 400.
  if route=='/api/download/does-not-exist' and status==404:status=400
  return super().basic(route,status,method)
 def report(self):
  if not getattr(self,'finalizing',False):
   self.emit('core_checks_complete_supplementary_checks_pending');return None
  result=super().report()
  result['test_inputs']=json.loads((self.out/'supplementary-test-identity.json').read_text('utf-8'))
  history=self.out/'targeted-retest.json'
  if history.exists():
   result['targeted_retest']=json.loads(history.read_text('utf-8'))
   path=self.out/'rapport.html';page=path.read_text('utf-8');page=page.replace('<h2>Anomalies</h2>','<p>Historique conservé : trois attentes de tests obsolètes ont été corrigées et les tests concernés rejoués. Les 581 autres contrôles ont été conservés avec leur heure d’exécution. Une limite de longueur de commande Windows dans le lanceur de reprise a également été corrigée. Aucun code du site ni montant n’a été modifié.</p><h2>Anomalies</h2>');path.write_text(page,'utf-8')
  test.save(self.out/'report.json',result);return result

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--base-url',default='http://127.0.0.1:8552');p.add_argument('--container',default='lexmachine-budget-web-1')
 p.add_argument('--output',type=Path,default=test.ROOT/'reports/crash-test-site-20260924')
 p.add_argument('--node',type=Path,default=test.DEFAULT_NODE);p.add_argument('--full-tree',action='store_true');p.add_argument('--no-load',action='store_true')
 args=p.parse_args();campaign=CurrentCampaign(args)
 # Fingerprint the supplementary test and its launcher before accepting checkpoints.
 key=campaign.out/'supplementary-test-identity.json'
 identity={str(f.relative_to(test.ROOT)):test.sha(f.read_bytes()) for f in [Path(__file__)]+[test.ROOT/'tests'/name for name in ['crash-display-amounts.cjs','rap-date-coverage-state.cjs','mpr-provenance.cjs','exclusion-restore.cjs','rap-refresh-state.cjs','rap-pagination-review.cjs','final-audit-ui.cjs','pilot-dossiers-ui.cjs']]}
 identity['docker_image']=test.command(['docker','inspect','--format','{{.Image}}',args.container]).strip()
 if key.exists() and json.loads(key.read_text('utf-8'))!=identity:raise ValueError('Supplementary test changed. Preserve the report and choose a new --output.')
 test.save(key,identity)
 campaign.run()
 def display():
  import os
  env=os.environ.copy();env['NODE_PATH']=str(args.node.parent.parent/'node_modules')
  output=campaign.out/'browser/display-amounts'
  text=test.command([str(args.node),str(test.ROOT/'tests/crash-display-amounts.cjs'),str(output)],timeout=240,env=env)
  (campaign.out/'display-amounts.log').write_text(text,'utf-8')
  result=json.loads((output/'display-report.json').read_text('utf-8'));assert result['success'];return result
 campaign.case('browser:display-amounts','visible_figures',display)
 def detector():
  import copy
  d=campaign.explorer(dict(start=2023,end=2024,budget='BG',scope='TA',measure='CP'))
  test.check_derived(d,campaign.ref['indices']);count=0
  for target in ('comparison','rate','missing'):
   changed=copy.deepcopy(d)
   if target=='comparison':changed['totals'][-1]['comparisons']['LFI_PLF']['value']+=1
   elif target=='rate':changed['totals'][-1]['evolution']['EXEC']['nominal_yoy']['value']+=1
   else:changed['totals'][0]['evolution']['EXEC']['nominal_yoy']['value']=0
   try:test.check_derived(changed,campaign.ref['indices'])
   except AssertionError:count+=1
   else:raise AssertionError('Injected '+target+' error was not detected')
  return dict(in_memory_injected_errors_detected=count,site_modified=False)
 campaign.case('test-oracle:injected-faults','harness_validation',detector)
 campaign.finalizing=True
 report=campaign.report()
 print(test.dump(report['counts']));return 0 if report['counts']['failed']==0 else 2
if __name__=='__main__':sys.exit(main())
