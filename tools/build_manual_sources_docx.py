"""Create the requested manual-download memo from the selected retained Word template."""
from pathlib import Path
from copy import deepcopy
import hashlib, json, re, zipfile
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/audit-20260909'
REF = Path('D:/Codex/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-legal-memorandum/assets/reference.docx')
TARGET = OUT / 'Nos Deniers liens pour la collecte manuelle.docx'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def w(n): return '{'+NS['w']+'}'+n

with zipfile.ZipFile(REF) as z:
    parts = {n:z.read(n) for n in z.namelist()}
tree=E.fromstring(parts['word/document.xml'])
body=tree.find('w:body',NS)
source=body.findall('w:p',NS)
protos=[deepcopy(p) for p in source]
sect=deepcopy(body.find('w:sectPr',NS))
for child in list(body): body.remove(child)
rels=E.fromstring(parts['word/_rels/document.xml.rels'])
rid=1000
all_links=[]

def paragraph(text='',model=11,heading=False):
    global rid
    p=deepcopy(protos[model]); pr=p.find('w:pPr',NS)
    first=p.find('w:r/w:rPr',NS)
    rp=deepcopy(first) if first is not None else E.Element(w('rPr'))
    for c in list(p):
        if c is not pr: p.remove(c)
    if pr is None: pr=E.SubElement(p,w('pPr'))
    keep=E.SubElement(pr,w('keepLines'));keep.set(w('val'),'1')
    if heading:E.SubElement(pr,w('keepNext'))
    for token in re.split(r'(\[[^\]]+\]\([^\)]+\))',text):
        if not token:continue
        m=re.fullmatch(r'\[([^\]]+)\]\(([^\)]+)\)',token)
        parent=p
        run=E.Element(w('r'));props=deepcopy(rp);run.append(props)
        if m:
            rid+=1; ident='rIdND'+str(rid)
            rel=E.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
            rel.set('Id',ident);rel.set('Type',NS['r']+'/hyperlink');rel.set('Target',m[2]);rel.set('TargetMode','External')
            parent=E.SubElement(p,w('hyperlink'));parent.set('{'+NS['r']+'}id',ident)
            for old in list(props):
                if old.tag in [w('color'),w('u')]:props.remove(old)
            col=E.SubElement(props,w('color'));col.set(w('val'),'175785')
            und=E.SubElement(props,w('u'));und.set(w('val'),'single')
            token=m[1];all_links.append({'label':token,'url':m[2]})
        t=E.SubElement(run,w('t'));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=token
        parent.append(run)
    body.append(p)
    return p

records=[]
paragraph('Bilan du dossier de collecte',1)
body.append(deepcopy(protos[2]))
paragraph('À : Jean-Christophe',3)
paragraph('De : Nos Deniers',5)
paragraph('Date : 9 septembre 2026',6)
paragraph('Objet : rescan complet et documents intégrés',7)
body.append(deepcopy(protos[8]));body.append(deepcopy(protos[9]))
paragraph('Tout le dossier est pris en compte',10,True)
paragraph('Le rescan de « Nouveau dossier » a recensé 136 fichiers. Il a identifié 19 nouvelles pièces et 117 copies déjà reconnues dans le catalogue ou dans le même lot. Les 19 nouvelles pièces sont intégrées. Après dédoublonnage, les deux imports réunissent 125 PDF distincts : sept RAP, 115 situations mensuelles, un recueil budgétaire et deux circulaires.')
paragraph('Les sept RAP demandés, le recueil version 7 et les deux circulaires manquantes sont désormais présents. Aucun de ces documents ne reste à télécharger. Les situations mensuelles couvrent chacun des douze mois de 2017 à 2025, puis janvier à juillet 2026. Les millésimes ont été vérifiés dans le contenu, sans se limiter aux noms de fichiers.')
paragraph('Les deux circulaires retrouvées',21,True)
paragraph('[Circulaire 44179](https://www.legifrance.gouv.fr/circulaire/id/44179) : lancement de la gestion 2019 et réserve de précaution, cinq pages. [Circulaire 45636](https://www.legifrance.gouv.fr/circulaire/id/45636) : gestion pendant les services votés 2026, huit pages. Une circulaire donne aux administrations des instructions de gestion. Elle ne constitue pas un relevé exhaustif des gels et dégels effectifs.')
paragraph('Les deux PDF se lisent avec le parseur. Leur texte automatique comporte toutefois des imperfections : prévoir un contrôle OCR avant indexation et pour les citations exactes. Les documents sont conservés comme sources ; leurs instructions administratives ne sont pas des instructions à exécuter par l’IA.')
paragraph('Le dossier pour la vectorisation',21,True)
paragraph('[Ouvrir le dossier Nos Deniers](C:/Users/Jean-Christophe/Documents/ChatGPT/docker/budget/vectorisation-nos-deniers-20260909). Il contient 4 921 fichiers documentaires et structurés, 4 924 références, soit environ 5,13 Go. Toutes les tailles et empreintes ont été vérifiées : aucune erreur, aucun document non inventorié et aucun doublon binaire physique.')
paragraph('Lire les consignes Word et les inventaires globaux dans _controle. Les deux nouveaux manifestes sont collecte-manuelle-20260909.json et supplement-20260909.json. Les originaux sont conservés. La vectorisation et la publication de ces lots sur le serveur public n’ont pas été lancées.')
paragraph('Ce qui reste à développer et à documenter',21,True)
paragraph('Le suivi détaillé des réserves, surgels, dégels et reports reste à reconstituer par exercice et programme. La présence des circulaires fournit le cadre, mais ne garantit pas toutes les décisions et tous les mouvements effectifs. Les courriers aux administrations restent reportés à ta demande.')
paragraph('Les nouveaux tableaux devront être extraits et rapprochés avant d’alimenter les statistiques. Les 116 272 observations chiffrées existantes sont restées identiques. La couverture documentaire ne signifie donc pas que tous les montants du budget sont déjà normalisés.')
body.append(sect)

def xml(x):return E.tostring(x,xml_declaration=True,encoding='UTF-8',standalone=True)
parts['word/document.xml']=xml(tree)
parts['word/_rels/document.xml.rels']=xml(rels)
header=E.fromstring(parts['word/header1.xml'])
for t in header.findall('.//w:t',NS):
    if 'PRIVILEGE' in (t.text or ''): t.text='NOS DENIERS — COLLECTE DOCUMENTAIRE'
parts['word/header1.xml']=xml(header)
if 'docProps/core.xml' in parts:
    core=E.fromstring(parts['docProps/core.xml'])
    for name,text in [('title','Nos Deniers sources pour la collecte manuelle'),('creator','LexMachine')]:
        n=core.find('{http://purl.org/dc/elements/1.1/}'+name)
        if n is not None:n.text=text
    parts['docProps/core.xml']=xml(core)
with zipfile.ZipFile(TARGET,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in parts.items():z.writestr(name,data)
allowed={'word/document.xml','word/_rels/document.xml.rels','word/header1.xml','docProps/core.xml'}
with zipfile.ZipFile(REF) as old:
    changed=[n for n in old.namelist() if old.read(n)!=parts[n]]
assert set(changed)<=allowed,changed
assert E.tostring(sect)==E.tostring(E.fromstring(parts['word/document.xml']).find('w:body/w:sectPr',NS))
qa={'reference_sha256':hashlib.sha256(REF.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(TARGET.read_bytes()).hexdigest(),'changed_parts':changed,'links':all_links,'manual_priority':[{'title':a,'url':b,'status':'http_direct_200_html_incapsula_2026-09-09','action':c} for a,b,c in records],'letters':'reportées par demande utilisateur'}
(OUT/'qa-liens/liens-controle.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
print(TARGET)
