"""Validate the user-supplied PDFs and prepare a reversible catalogue import."""
import collections, hashlib, json, re, unicodedata
from pathlib import Path
from datetime import datetime, timezone
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/Jean-Christophe/Desktop/Nouveau dossier')
OUT=ROOT/'reports/import-nouveau-dossier-20260909'
OUT.mkdir(exist_ok=True)
manifest_path=ROOT/'reports/MANIFEST-COLLECTE.json'
original=json.loads(manifest_path.read_text(encoding='utf-8'))
records=json.loads(json.dumps(original));known={r['sha256']:r for r in records if r.get('sha256')};old_hashes=set(known)
export=ROOT/'vectorisation-nos-deniers-20260909'
prior_export=json.loads((export/'_controle/export-inventaire-global.json').read_text(encoding='utf-8'))
export_hashes={r['sha256']:r['export_relative_path'] for r in prior_export['references']}
now=datetime.now(timezone.utc).isoformat();items=[];new=[];validation=[];errors=[]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if not unicodedata.combining(c))
for i,p in enumerate(sorted(SOURCE.rglob('*')),1):
    if not p.is_file():continue
    before=p.stat();h=sha(p);item={'filename':p.relative_to(SOURCE).as_posix(),'bytes':before.st_size,'sha256':h}
    try:
        if p.suffix.lower()!='.pdf':raise ValueError('Unsupported format; kept for review')
        reader=PdfReader(p,strict=False)
        if reader.is_encrypted and reader.decrypt('')==0:raise ValueError('Encrypted PDF')
        pages=len(reader.pages);head=[]
        for j,page in enumerate(reader.pages):
            content=page.get_contents()
            if content is not None:content.get_data()
            if j<3:head.append(page.extract_text() or '')
        text='\n'.join(head);item.update(pages=pages,head_text=text[:14000],text_extractable=bool(text.strip()),validation='all page content streams decoded; first three pages text extracted')
        if sha(p)!=h or p.stat().st_size!=before.st_size:raise ValueError('Source changed during validation')
        n=norm(p.name);nt=norm(text)
        stage='rap' if re.search(r'rap20|_plr_',n) else 'recueil_comptabilite' if 'recueil' in n else 'situation_mensuelle' if ('mensuel' in n or 'smb' in n) else 'circulaire' if 'circulaire' in n or re.search(r'cir_\d',n) else 'document'
        year_match=re.search(r'20\d{2}',p.name)
        if not year_match:year_match=re.search(r'20\d{2}',text[:1600])
        year=year_match.group(0) if year_match else None
        title=p.stem.replace('_',' ')
        item.update(stage=stage,year=year,export_already_present=export_hashes.get(h))
        record=known.get(h)
        if record: disposition='already_present' if h in old_hashes else 'duplicate_in_batch'
        else:
            slug=re.sub(r'[^A-Za-z0-9_-]+','-',unicodedata.normalize('NFKD',p.stem).encode('ascii','ignore').decode()).strip('-')[:100]
            record={'path':f'public/manual/nouveau-dossier-20260909/{stage}/{slug}-{h[:12]}.pdf','title':title,'years_title':[year] if year else [],'format':'pdf','role':'official_document','status':'downloaded','checked_at':now,'bytes':before.st_size,'sha256':h,'pages':pages,'text_extractable':bool(text.strip()),'original_filename':p.name,'provenance':'Fichier fourni par l’utilisateur depuis Bureau/Nouveau dossier ; identité documentaire contrôlée dans le PDF, URL de téléchargement non certifiée','url':'','import_batch':'nouveau-dossier-20260909','numeric_import':False,'document_stage':stage}
            records.append(record);known[h]=record;new.append(record);disposition='new'
        item.update(path=record['path'],disposition=disposition)
        items.append({k:item[k] for k in ['filename','path','sha256','bytes','disposition']});validation.append(item)
    except Exception as e:errors.append(dict(item,error=type(e).__name__+': '+str(e)[:400]))
    if i%20==0:print('Validated',i,flush=True)
summary={'files':len(validation)+len(errors),'valid_pdf_references':len(validation),'errors':len(errors),'dispositions':dict(collections.Counter(x['disposition'] for x in items)),'new_formats':{'pdf':len(new)},'new_years':dict(collections.Counter(','.join(r['years_title']) or 'unknown' for r in new)),'new_bytes':sum(r['bytes'] for r in new),'old_sources':len(original),'new_sources':len(records),'pages':sum(x['pages'] for x in validation)}
plan={'at':now,'base_manifest_sha256':sha(manifest_path),'items':items,'new_records':new,'summary':summary}
for name,value in [('plan.json',plan),('manifest-merged.json',records),('validation.json',{'summary':summary,'files':validation,'errors':errors})]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True));print(json.dumps(errors,ensure_ascii=True))
