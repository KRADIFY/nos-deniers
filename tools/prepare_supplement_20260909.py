from pathlib import Path
import json,hashlib,shutil,re,unicodedata,collections
from pypdf import PdfReader
R=Path(__file__).resolve().parents[1];B=R/'reports/import-supplement-20260909';B.mkdir(exist_ok=True);I=B/'incoming';I.mkdir(exist_ok=True)
names=['Situation mensuelle du budget de l\'Etat au 31 octobre 2025.pdf','Recueil des regles de comptabilite budgetaire de l\'Etat - Version 7.pdf','FR_2024_PLR_BG_MSN_SE (2).pdf','FR_2023_PLR_BG_MSN_AD (1).pdf','FR_2024_PLR_BG_MSN_SE (1).pdf','RAP2025_BG_Ecologie_developpement_mobilites_durables_TA (1).pdf','RAP2025_BG_Defense_DA (1).pdf','RAP2025_BG_Investir_France_2030_AV (1).pdf','RAP2025_BG_Plan_relance_PR (1).pdf','RAP2025_CS_CAS_Developpement_agricole_rural_YF (1).pdf','cir_45636 (1).pdf','Recueil des regles de comptabilite budgetaire de l\'Etat - Version 7 (1).pdf','cir_45636.pdf','cir_44179.pdf','cir_44179 (1).pdf','situation_mensuelle_budget_Etat_31072019.pdf','situation_mensuelle_budget_Etat_30062019.pdf','36 - Situation mensuelle budgetaire au 31 octobre 2024.pdf','1824 - Situation mensuelle budgetaire au 31 mars 2024.pdf','1908 - Situation mensuelle budgetaire au 24 avril 2024.pdf','Situation mensuelle budgetaire au 30 novembre 2024.pdf','105 - CP - Situation mensuelle budgetaire au 31 decembre 2024.pdf']
names+=['Situation mensuelle du budget de l\'Etat '+s+'.pdf' for s in ['au 31 janvier 2025','au 28 fevrier 2025','au 31 mars 2025','au 30 avril 2025','au 31 mai 2025','au 30 juin 2025','au au 31 juillet 2025','au 31 aout 2025','au 30 septembre 2025']]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(t):return ''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if not unicodedata.combining(c))
mp=R/'reports/MANIFEST-COLLECTE.json';old=json.loads(mp.read_text(encoding='utf-8'));known={r['sha256']:r for r in old};new=[];items=[];checks=[]
months='janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre'.split()
source=Path('C:/Users/Jean-Christophe/Desktop/Nouveau dossier')
names=[p.relative_to(source).as_posix() for p in sorted(source.rglob('*')) if p.is_file()]
for name in names:
 p=source/name;h=sha(p)
 if h in known:checks.append({'file':name,'sha256':h,'status':'duplicate','catalogue_path':known[h]['path']});continue
 reader=PdfReader(p);text='\n'.join(pg.extract_text() or '' for pg in list(reader.pages)[:3]);t=norm(text)
 for pg in reader.pages:
  content=pg.get_contents()
  if content is not None:content.get_data()
 if name.startswith('cir_'):
  cid=re.search(r'cir_(\d+)',name)[1];year='2019' if cid=='44179' else '2026';stage='circulaire';month=None
  title='Lancement de la gestion budgétaire 2019 et mise en place de la réserve de précaution' if year=='2019' else 'Gestion budgétaire pendant la période des services votés en 2026'
  url='https://www.legifrance.gouv.fr/circulaire/id/'+cid
 else:
  match=re.search(r'\bau\s+\d{1,2}\s+('+'|'.join(months)+r')\s+(20\d{2})',t);assert match,name
  year=match[2];month=months.index(match[1])+1;stage='situation_mensuelle';title=p.stem;url=''
 slug=re.sub('[^A-Za-z0-9_-]+','-',norm(p.stem))[:110];path=f'public/manual/supplement-20260909/{slug}-{h[:12]}.pdf'
 row=dict(path=path,title=title,years_title=[year],document_month=month,document_stage=stage,format='pdf',role='official_document',status='downloaded',bytes=p.stat().st_size,sha256=h,pages=len(reader.pages),text_extractable=bool(text.strip()),original_filename=name,url=url,provenance='Fichier fourni par l’utilisateur ; identité vérifiée dans le PDF',numeric_import=False,import_batch='supplement-20260909',extraction_note='Texte extrait automatiquement susceptible de nécessiter une correction OCR' if stage=='circulaire' else '')
 new.append(row);known[h]=row;(I/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,I/name);items.append(dict(filename=name,path=path,sha256=h,bytes=row['bytes'],disposition='new'));checks.append(dict(file=name,status='new',sha256=h,year=year,month=month,pages=len(reader.pages),stage=stage))
summary=dict(files=len(names),new_sources=len(old)+len(new),old_sources=len(old),new_files=len(new),duplicates=len(names)-len(new),pages=sum(r['pages'] for r in new),stages=dict(collections.Counter(r['document_stage'] for r in new)))
for n,data in [('plan.json',dict(base_manifest_sha256=sha(mp),new_records=new,items=items,summary=summary)),('manifest-merged.json',old+new),('validation.json',dict(summary=summary,files=checks))]:
 (B/n).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary));print(json.dumps([x for x in checks if x['status']=='new'],ensure_ascii=False))
