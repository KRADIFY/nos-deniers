from pathlib import Path
p=Path('install.py');s=p.read_text('utf-8').replace('shutil.copytree(BUNDLE,target)',"""target.mkdir(parents=True)
    for name in list(manifest)+['FILES.json']:
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BUNDLE/name,dest)""")
s=s.replace("run(['docker','build','-t',image,str(target)])", """run(['docker','build','-t',image,str(target)])
    isolated=['docker','run','--rm','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:size=384m,mode=1777','--shm-size','256m']
    run(isolated+['--mount','type=bind,source='+str(target)+',target=/tests,readonly',image,'python','-m','unittest','discover','-s','/tests','-p','test_*.py','-q'])
    smoke=\"const {chromium}=require(process.env.AUDIT_NODE_MODULES+'/playwright');(async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.AUDIT_CHROME});const p=await b.newPage();await p.setContent('<h1>Test audit</h1>');if(await p.locator('h1').textContent()!=='Test audit')throw Error('Navigateur invalide');await b.close();console.log('Navigateur Docker vérifié.');})().catch(e=>{console.error(e);process.exit(1)})\"
    run(isolated+[image,'node','-e',smoke])""")
p.write_text(s,'utf-8')
p=Path('site_link.py');s=p.read_text('utf-8').replace("def patch(html,css):", "def patch(html,css):")
p.write_text(s,'utf-8')
p=Path('web/zeros.js');s=p.read_text('utf-8').replace("function text(tag,content)","const stages={PLF:'Proposé en PLF',LFI:'Voté en LFI',EXEC:'Consommé',OUVERT:'Crédits ouverts',REPORT_ENTRANT:'Reports de N−1',REPORT_SORTANT:'Reports vers N+1',FDC:'FdC et AdP rattachés',FDC_PREVU:'FdC et AdP prévus',REGLEMENT:'Mouvements réglementaires',LEGIS:'Ajustements législatifs',FONGIBILITE:'Fongibilité',PLRG_OUVERTURE:'Ouvertures en PLRG',PLRG_ANNULATION:'Annulations en PLRG'};\nfunction text(tag,content)").replace("[item.year,item.measure,item.stage]", "[item.year,item.measure,stages[item.stage]||item.stage]")
p.write_text(s,'utf-8')
