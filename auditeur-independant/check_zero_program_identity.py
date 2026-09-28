"""Confirm that a cited PDF page belongs to the fact's programme."""
import json,re,shutil,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from document_zeros import ordered
groups=json.loads(Path('resultats/document-zero-inputs.json').read_text('utf-8'));root=Path('references/physical-sources');out=Path('resultats/document-zero-pages')
data=json.loads(Path('document-zero-proofs.json').read_text('utf-8'));catalog={g['source']['id']:g['source'] for g in groups}
cache={};anchors={};missing=[]
for proof in data['proofs']:
    if proof['kind']!='pdf':continue
    f=proof['fact'];sid=f['source'];page=proof['page'];key=(sid,page,f['program'])
    if key in anchors:continue
    if any(x['role']=='program' for x in proof['fragments']):anchors[key]=None;continue
    if sid not in cache:
        dest=out/(sid+'-identity-full.txt')
        subprocess.run([shutil.which('pdftotext'),'-layout',str(root/catalog[sid]['path']),str(dest)],check=True,capture_output=True)
        cache[sid]=dest.read_text('utf-8').split('\f')
    pages=cache[sid];match=None
    # Search backwards, stopping at the nearest explicit programme identifier.
    for n in range(page-1,-1,-1):
        ids=list(re.finditer(r'(?i)programme\s*(?:n[°ºo]\s*)?([0-9]{3})\b',pages[n]))
        if not ids:continue
        # Headings must stand alone or contain Programme n°, not a narrative reference.
        ids=[m for m in ids if 'n°' in m.group().lower() or pages[n][max(0,m.start()-2):m.start()].strip()=='']
        if not ids:continue
        matching=[m for m in ids if m[1]==f['program']]
        if not matching:break
        match=(n+1,matching[0].group());break
    if not match:missing.append(key);continue
    n,phrase=match;dest=out/f'{sid}-identity-{n}.xml'
    subprocess.run([shutil.which('pdftotext'),'-f',str(n),'-l',str(n),'-bbox-layout',str(root/catalog[sid]['path']),str(dest)],capture_output=True,check=True)
    doc=ET.parse(dest);ws=[dict(text=w.text or '',**{k:float(v) for k,v in w.attrib.items()}) for w in doc.iter() if w.tag.endswith('}word')]
    found=[]
    for w in ws:
        if w['text']!=f['program']:continue
        nearby=[v for v in ws if abs((v['yMin']+v['yMax'])/2-(w['yMin']+w['yMax'])/2)<2 and w['xMin']-120<v['xMin']<=w['xMin']]
        if re.search(r'(?i)programme\s*(?:n[°ºo]\s*)?'+f['program']+r'\b',ordered(nearby)):found=nearby;break
    if not found:missing.append(key);continue
    box=[min(w['xMin'] for w in found)-.1,min(w['yMin'] for w in found)-.1,max(w['xMax'] for w in found)+.1,max(w['yMax'] for w in found)+.1]
    anchors[key]=dict(role='program',page=n,box=box,text=ordered(found))
for p in data['proofs']:
    if p['kind']=='pdf':
        anchor=anchors.get((p['fact']['source'],p['page'],p['fact']['program']))
        if anchor:p['fragments'].append(anchor)
Path('document-zero-proofs.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
print('Programme identities located',len(anchors),'Not located',missing)
