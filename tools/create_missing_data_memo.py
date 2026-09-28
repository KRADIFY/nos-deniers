from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "reports" / "final-audit-20260920"
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = OUTDIR / "Nos Deniers - Rendre disponibles les donnees manquantes.docx"

NAVY = "173A5E"
PALE = "EAF1F7"
PALE2 = "F5F7F9"
BORDER = "D9D9D9"
DARK = RGBColor(0, 0, 0)
MUTED = RGBColor(74, 85, 104)
ACCENT = RGBColor(23, 58, 94)

def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:fill"), fill)

def set_cell_margins(cell, top=100, start=120, bottom=100, end=120):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn("w:" + m))
        if node is None:
            node = OxmlElement("w:" + m)
            tcMar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")

def set_table_borders(table, color=BORDER, size="6"):
    tblPr = table._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        node = borders.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)

def remove_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        node = borders.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            borders.append(node)
        node.set(qn("w:val"), "nil")

def set_repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    trPr.append(header)

def set_cell_width(cell, cm):
    tcPr = cell._tc.get_or_add_tcPr()
    tcW = tcPr.find(qn("w:tcW"))
    if tcW is None:
        tcW = OxmlElement("w:tcW")
        tcPr.append(tcW)
    tcW.set(qn("w:w"), str(int(cm * 567)))
    tcW.set(qn("w:type"), "dxa")

def add_hyperlink(paragraph, text, url, color="173A5E"):
    part = paragraph.part
    rid = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    c = OxmlElement("w:color")
    c.set(qn("w:val"), color)
    rPr.append(c)
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)
    run.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    return hyperlink

def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.addnext(fld)

def add_bullet(text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.add_run(text)
    return p

def add_step(number, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.65)
    p.paragraph_format.first_line_indent = Cm(-0.65)
    r = p.add_run(f"{number}.  ")
    r.bold = True
    p.add_run(text)
    return p

def add_table(headers, rows, widths, aligns=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblPr = table._tbl.tblPr
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tblPr.append(layout)
    layout.set(qn("w:type"), "fixed")
    set_table_borders(table)
    hdr = table.rows[0]
    set_repeat_header(hdr)
    for i, (cell, text, width) in enumerate(zip(hdr.cells, headers, widths)):
        set_cell_width(cell, width)
        set_cell_shading(cell, NAVY)
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        r.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(8.5)
    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for i, (cell, text, width) in enumerate(zip(cells, row, widths)):
            set_cell_width(cell, width)
            set_cell_margins(cell, top=90, bottom=90)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if ridx % 2:
                set_cell_shading(cell, PALE2)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            if aligns and aligns[i] == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(str(text))
            r.font.size = Pt(8.3)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table

doc = Document()
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = Cm(1.7)
section.bottom_margin = Cm(1.6)
section.left_margin = Cm(1.8)
section.right_margin = Cm(1.8)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Aptos"
normal._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
normal.font.size = Pt(10)
normal.font.color.rgb = DARK
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.08

title = styles["Title"]
title.font.name = "Aptos Display"
title._element.rPr.rFonts.set(qn("w:ascii"), "Aptos Display")
title._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos Display")
title.font.size = Pt(26)
title.font.bold = True
title.font.color.rgb = DARK
title.paragraph_format.space_after = Pt(10)
title_pPr = title._element.get_or_add_pPr()
title_border = title_pPr.find(qn("w:pBdr"))
if title_border is not None:
    title_pPr.remove(title_border)

for name, size, before, after in [("Heading 1", 16, 14, 7), ("Heading 2", 12, 10, 5)]:
    st = styles[name]
    st.font.name = "Aptos Display"
    st._element.rPr.rFonts.set(qn("w:ascii"), "Aptos Display")
    st._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos Display")
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = DARK
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

if "Memo subtitle" not in [s.name for s in styles]:
    st = styles.add_style("Memo subtitle", WD_STYLE_TYPE.PARAGRAPH)
    st.font.name = "Aptos"
    st._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    st._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    st.font.size = Pt(13)
    st.font.color.rgb = MUTED
    st.paragraph_format.space_after = Pt(20)

# Footer
footer = section.footer
footer.paragraphs[0].text = ""
footer.paragraphs[0].paragraph_format.space_after = Pt(0)
ft = footer.add_table(rows=1, cols=2, width=Cm(17.4))
ft.autofit = False
remove_table_borders(ft)
left, right = ft.rows[0].cells
set_cell_width(left, 13.8)
set_cell_width(right, 3.6)
lp = left.paragraphs[0]
lp.paragraph_format.space_after = Pt(0)
lr = lp.add_run("Nos Deniers   Mémo opérationnel   20 septembre 2026")
lr.font.size = Pt(8)
lr.font.color.rgb = MUTED
rp = right.paragraphs[0]
rp.paragraph_format.space_after = Pt(0)
add_page_number(rp)
for run in rp.runs:
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED

# First page
p = doc.add_paragraph()
p.style = styles["Title"]
p.add_run("Rendre disponibles les données encore manquantes dans Nos Deniers")
p = doc.add_paragraph(style="Memo subtitle")
p.add_run("Méthode de collecte, demandes administratives et critères de publication")
p = doc.add_paragraph()
r = p.add_run("Destinataires : ")
r.bold = True
p.add_run("équipe LexMachine et assistante parlementaire utilisant le service pour le contrôle budgétaire.")
p = doc.add_paragraph()
r = p.add_run("Conclusion opérationnelle. ")
r.bold = True
p.add_run("Les données actuellement absentes ne relèvent pas toutes du même problème. Une partie se trouve déjà dans les RAP mais doit être relue et rapprochée manuellement. Une deuxième partie est publique mais dispersée. La dernière partie, notamment les extractions fines de gestion et certains gels ou dégels en cours d’année, devra être demandée aux administrations qui produisent les données.")
p = doc.add_paragraph()
p.add_run("La bonne stratégie consiste à publier quatre états distincts : disponible et rapproché, disponible partiellement, preuve documentaire sans montant exploitable, indisponible. Aucun total de programme, montant global de l’Anah ou blanc de tableau ne doit être utilisé comme estimation d’un dispositif.")
doc.add_heading("Ce qui peut être rendu disponible sans nouvelle demande", level=1)
add_bullet("Les 128 groupes d’actions RAP écartés, après résolution des changements de nomenclature, des doublons et des écarts de rapprochement.")
add_bullet("Les 223 pages candidates de mouvements, après reprise des 160 échecs de lecture et des 62 écarts de calcul.")
add_bullet("Les 16 tables de réserves encore ambiguës, après contrôle des lignes manquantes, des colonnes et des erreurs arithmétiques imprimées.")
add_bullet("Les documents publics déjà collectés ou indexés, dès lors qu’une page, une unité, un périmètre et un total de contrôle peuvent être établis.")
doc.add_heading("Ce qui exigera probablement une demande", level=1)
add_bullet("Le périmètre national complet de MaPrimeRénov’ en 2020.")
add_bullet("Pour 2025 : AE du PLF, LFI, crédits ouverts, consommation, mouvements, reports et réserves propres au dispositif.")
add_bullet("Pour 2026 : montants MaPrimeRénov’ ventilés par étape budgétaire, programme et nature de mouvement.")
add_bullet("Les extractions Chorus ou Chorus Décisionnel donnant une lecture homogène et datée de la gestion, notamment lorsqu’aucun tableau public n’isole le dispositif.")

doc.add_page_break()
doc.add_heading("État précis des lacunes", level=1)
p = doc.add_paragraph()
p.add_run("Point de départ vérifié le 20 septembre 2026. ").bold = True
p.add_run("La base contient 120 948 faits canoniques. Les registres dérivés n’écrasent pas ces faits et ne publient que les tables rapprochées.")
add_table(
    ["Donnée", "État actuel", "Pourquoi elle manque", "Voie de résolution"],
    [
        ["MaPrimeRénov’ 2020", "Partiel", "P174 chiffré en LFI et consommé ; périmètre national complet non démontré.", "Jaunes, PAP et RAP 2020 ; sinon tableau DHUP ou Anah rapproché des crédits de l’État."],
        ["MaPrimeRénov’ 2021 à 2023", "Consommé disponible", "PLF, LFI et ouverts ne sont pas tous isolés du dispositif.", "Rechercher les tableaux annuels de financement puis demander l’export manquant."],
        ["MaPrimeRénov’ 2024", "LFI, ouverts et consommé disponibles", "PLF manquant ; périmètre des aides évolutif.", "Jaune budgétaire, PAP et documents Anah avec contrôle des définitions."],
        ["MaPrimeRénov’ 2025", "PLF CP disponible : 1 378 M€", "Les autres étapes restent agrégées avec d’autres aides ou documentées seulement par le transfert au P135.", "Demande ciblée DHUP, Anah et direction du Budget."],
        ["MaPrimeRénov’ 2026", "Preuve documentaire seulement", "Le chiffre politique de 3,6 Md€ ne définit pas à lui seul AE, CP, source de financement ni étape.", "Obtenir le tableau budgétaire détaillé et son dictionnaire de périmètre."],
        ["Actions RAP", "1 231 groupes publiables ; 128 écartés", "Parents canoniques absents, écarts de somme, doublons ou source incertaine.", "Relecture interne ; demander uniquement les RAP réellement absents."],
        ["Mouvements", "126 programme-années publiables", "223 pages candidates non promues, surtout à cause de mises en page ou de rapprochements.", "Extraction adaptée puis contrôle ; export Chorus si aucun tableau ne suffit."],
        ["Réserves", "264 programme-années publiables", "16 tables encore ambiguës et détail temps réel inégal.", "Relecture ; demandes aux DAF, CBCM et direction du Budget pour le solde fin."],
    ],
    [3.1, 3.0, 5.1, 5.2],
)
p = doc.add_paragraph()
r = p.add_run("Point important sur MaPrimeRénov’. ")
r.bold = True
p.add_run("Le montant de 3,6 Md€ annoncé pour 2026 par le ministère constitue une information officielle utile, mais il ne doit pas être injecté directement dans une cellule PLF, LFI, ouvert ou consommé sans document précisant la nature de l’enveloppe, les programmes concernés et la distinction entre crédits de l’État et ressources de l’Anah.")

doc.add_heading("Définition de disponible dans le site", level=1)
add_table(
    ["Statut", "Condition", "Affichage"],
    [
        ["Disponible", "Montant exact, unité, étape, AE ou CP, périmètre, source et page ; total rapproché.", "Valeur calculable, exportable et justifiable."],
        ["Partiel", "Une partie du périmètre seulement est documentée.", "Valeur limitée au périmètre connu, avec avertissement visible."],
        ["Preuve documentaire", "Le transfert, l’existence ou l’absence dans un programme est prouvé, sans montant national complet.", "Justification et citations, sans total inventé."],
        ["Indisponible", "Aucune source assez fine ou rapprochement non concluant.", "Cellule grisée et explication de la donnée attendue."],
    ],
    [2.8, 8.0, 5.6],
)

doc.add_page_break()
doc.add_heading("Plan de récupération", level=1)
doc.add_heading("Étape 1 Relire ce qui est déjà dans la base", level=2)
add_step(1, "Reprendre les pages écartées par famille de mise en page, sans relancer la vectorisation générale.")
add_step(2, "Identifier le tableau d’origine, son année, sa mission, son programme, son unité et ses colonnes AE et CP.")
add_step(3, "Rattacher chaque ligne au fait canonique PLF, LFI ou consommé correspondant.")
add_step(4, "Recalculer les sommes et conserver l’écart imprimé lorsqu’il vient du document.")
add_step(5, "Promouvoir uniquement les lignes dont le rapprochement est exact ou dont l’arrondi est explicitement documenté.")
p = doc.add_paragraph()
p.add_run("Résultat attendu : ").bold = True
p.add_run("une partie importante des 128 groupes d’actions, 223 pages de mouvements et 16 tables de réserves peut être récupérée sans solliciter l’administration.")

doc.add_heading("Étape 2 Exploiter les sources publiques", level=2)
add_table(
    ["Source", "À y chercher", "Usage"],
    [
        ["budget.gouv.fr", "PAP, RAP, PLRG, circulaires, situations mensuelles, référentiels.", "Source budgétaire principale et pages de preuve."],
        ["Assemblée nationale", "Annexes aux PLF et PLRG, jaunes budgétaires, rapports de commission.", "Périmètres transversaux et explications des changements."],
        ["Journal officiel", "Décrets d’avance, annulations, arrêtés de reports, lois de finances rectificatives.", "Date, base juridique et signe des mouvements."],
        ["Anah et ministère du Logement", "Bilans MaPrimeRénov’, engagements, paiements et ventilation des aides.", "Complément dispositif ; à ne pas additionner automatiquement aux crédits de l’État."],
        ["Cour des comptes", "Notes d’exécution budgétaire, observations et tableaux de rapprochement.", "Contrôle indépendant et explication des écarts."],
    ],
    [3.5, 7.0, 5.9],
)

doc.add_heading("Étape 3 Demander des exports existants", level=2)
p = doc.add_paragraph()
p.add_run("Le document demandé doit être décrit avec précision. ").bold = True
p.add_run("Les informations d’une base sont communicables lorsqu’elles peuvent être extraites par un traitement automatisé d’usage courant. Il faut donc demander un export existant ou une extraction simple, sur une période et des champs définis, plutôt qu’une étude nouvelle.")
add_bullet("Pour MaPrimeRénov’ : DHUP et Anah pour le périmètre du dispositif ; direction du Budget et services financiers ministériels pour les crédits de l’État.")
add_bullet("Pour les gels, dégels et annulations : direction du Budget, direction des affaires financières du ministère et contrôleur budgétaire et comptable ministériel.")
add_bullet("Pour Chorus : demander d’abord le contenu au service producteur. L’AIFE exploite le système technique ; elle n’est pas nécessairement l’autorité compétente pour décider de la communication des données métier.")
add_bullet("Pour une nomenclature interministérielle : direction du Budget, avec tables de correspondance des missions, programmes, actions et sous-actions.")

doc.add_heading("Champs à demander dans chaque export", level=2)
add_table(
    ["Bloc", "Champs indispensables"],
    [
        ["Identification", "Exercice, budget, mission, programme, action, sous-action, codes et libellés."],
        ["Mesure", "AE ou CP ; montant en euros ; signe ; unité ; date d’arrêté ou date comptable."],
        ["Étape", "PLF, LFI, ouvert, consommé, FdC ou AdP prévus et encaissés, report entrant et sortant."],
        ["Gestion", "Réserve initiale, surgel, dégel, annulation, ouverture, virement, transfert, répartition."],
        ["Traçabilité", "Identifiant d’écriture ou d’acte, source, page ou référence, date d’extraction."],
        ["Périmètre MaPrimeRénov’", "Volet de l’aide, financeur, programme porteur, part crédits de l’État, part ressources Anah, absence ou présence d’autres dispositifs."],
    ],
    [4.0, 12.4],
)

doc.add_heading("Interlocuteurs à mobiliser", level=1)
add_table(
    ["Besoin", "Premier interlocuteur", "Interlocuteur complémentaire"],
    [
        ["Montants MaPrimeRénov’ par étape", "DGALN, DHUP et Anah", "Direction du Budget et DAF du ministère chargé du logement"],
        ["Crédits et mouvements de l’État", "Direction du Budget", "DAF et CBCM du ministère concerné"],
        ["Exports Chorus", "Service financier producteur ou détenteur", "AIFE pour la faisabilité et le format technique"],
        ["Gels et dégels", "Direction du Budget et CBCM", "Responsable de programme et DAF"],
        ["Correspondances de nomenclature", "Direction du Budget", "Responsables de programme"],
        ["Accès aux documents", "PRADA du ministère détenteur", "CADA en cas de refus ou de silence"],
    ],
    [5.0, 5.7, 5.7],
)
p = doc.add_paragraph()
p.add_run("Canal Transition écologique et logement. ").bold = True
p.add_run("La PRADA ministérielle peut être saisie à ")
add_hyperlink(p, "prada.sg@developpement-durable.gouv.fr", "mailto:prada.sg@developpement-durable.gouv.fr")
p.add_run(". Les questions relatives aux données, codes et algorithmes peuvent aussi être adressées à ")
add_hyperlink(p, "amd@developpement-durable.gouv.fr", "mailto:amd@developpement-durable.gouv.fr")
p.add_run(".")
p = doc.add_paragraph()
p.add_run("Canal ministères économiques et financiers. ").bold = True
p.add_run("Les demandes peuvent être adressées au Secrétariat général, BDA, secteur documentation externe, 139 rue de Bercy, 75572 Paris Cedex 12, ou via le formulaire officiel d’accès aux documents administratifs.")
p = doc.add_paragraph()
p.add_run("Canal parlementaire. ").bold = True
p.add_run("Si la députée est rapporteure spéciale, présidente ou rapporteure générale de la commission des finances, l’article 57 de la LOLF ouvre un droit de communication étendu sur les renseignements et documents financiers et administratifs. Dans les autres cas, une demande ministérielle signée par la députée, une question écrite ou la voie CRPA restent les moyens adaptés.")

doc.add_heading("Procédure CRPA et CADA", level=1)
add_step(1, "Adresser une demande écrite précise au ministère ou à l’organisme qui détient le document.")
add_step(2, "Conserver le courriel, la liste des champs, la période et l’accusé de réception.")
add_step(3, "En l’absence de réponse pendant un mois, ou après un refus, saisir la CADA.")
add_step(4, "Respecter le délai de deux mois à compter du refus pour la saisine de la CADA.")
add_step(5, "Demander une transmission électronique en CSV ou XLSX, avec le dictionnaire des champs et la date d’extraction.")
p = doc.add_paragraph()
r = p.add_run("Précaution. ")
r.bold = True
p.add_run("Une demande trop générale ou obligeant l’administration à reconstituer une étude complexe risque d’être rejetée. Il est préférable de viser un export existant, une restitution Chorus identifiée ou une extraction d’usage courant.")

doc.add_page_break()
doc.add_heading("Modèle de demande MaPrimeRénov’", level=1)
p = doc.add_paragraph()
p.add_run("Objet : Communication des tableaux de suivi budgétaire de MaPrimeRénov’ pour 2020, 2025 et 2026").bold = True
for para in [
    "Madame, Monsieur,",
    "Dans le cadre d’un travail parlementaire de suivi de l’exécution budgétaire, je souhaite obtenir, sous forme électronique réutilisable, les tableaux ou exports existants retraçant les crédits de l’État affectés à MaPrimeRénov’ pour les exercices 2020, 2025 et 2026.",
    "Pour chaque exercice, la demande porte sur les AE et les CP aux étapes PLF, LFI, crédits ouverts et consommation, ainsi que sur les reports, fonds de concours, attributions de produits, mises en réserve, surgels, dégels, annulations, virements et transferts lorsqu’ils existent.",
    "Je souhaite que l’export comporte les codes et libellés de mission, programme, action et sous-action, la date de chaque mouvement, le montant en euros, le programme porteur et, lorsque l’enveloppe inclut plusieurs dispositifs, la part propre à MaPrimeRénov’. Merci de distinguer les crédits du budget général de l’État des autres ressources de l’Anah et les différents volets de l’aide.",
    "Un fichier CSV ou XLSX accompagné du dictionnaire des champs et de la date d’extraction conviendrait. Si ces informations sont réparties dans plusieurs restitutions existantes, leur communication séparée est acceptable.",
    "Cette demande est formulée au titre du droit d’accès aux documents administratifs. Si votre service ne détient pas ces documents, je vous remercie de transmettre la demande au service compétent ou de m’indiquer lequel les détient.",
    "Je vous remercie par avance de votre réponse.",
    "Cordialement,"
]:
    doc.add_paragraph(para)

doc.add_page_break()
doc.add_paragraph()
doc.add_heading("Modèle de demande crédits gels et mouvements", level=1)
p = doc.add_paragraph()
p.add_run("Objet : Communication d’extractions budgétaires par programme et action").bold = True
for para in [
    "Madame, Monsieur,",
    "Afin de suivre l’exécution du budget de l’État, je souhaite obtenir les restitutions ou exports existants permettant, pour les exercices 2017 à 2026, de rapprocher les crédits votés, les crédits ouverts et les crédits consommés par mission, programme, action et sous-action.",
    "La demande porte sur les AE et les CP et, lorsqu’ils sont disponibles, sur la réserve initiale, le surgel, les dégels, les annulations, les ouvertures, virements, transferts, répartitions, reports entrants et sortants, fonds de concours et attributions de produits. Pour chaque ligne, merci d’indiquer le montant signé, la date, la référence de l’acte et l’état de gestion auquel il se rattache.",
    "Je souhaite recevoir un export CSV ou XLSX issu d’une restitution existante de Chorus ou Chorus Décisionnel, avec les codes et libellés de nomenclature et le dictionnaire des champs. La demande n’appelle pas la création d’une étude ou d’un commentaire nouveau.",
    "Si le volume est important, la transmission peut être organisée par exercice ou par mission. Une première livraison limitée aux missions et programmes présentant des données manquantes est également possible.",
    "Je vous remercie de transmettre la demande au service détenteur si nécessaire.",
    "Cordialement,"
]:
    doc.add_paragraph(para)

doc.add_page_break()
doc.add_paragraph()
doc.add_heading("Modèle de relance et saisine CADA", level=1)
p = doc.add_paragraph()
p.add_run("Objet : Relance d’une demande de communication de documents administratifs").bold = True
for para in [
    "Madame, Monsieur,",
    "Je vous ai adressé une demande de communication le [date d’envoi], reçue le [date de réception], concernant [désignation précise des tableaux ou exports].",
    "À ce jour, je n’ai pas reçu les documents demandés ni de décision motivée. Je vous remercie de bien vouloir me les transmettre au format électronique demandé ou de m’indiquer les motifs juridiques précis faisant obstacle à leur communication.",
    "À défaut de réponse, je saisirai la Commission d’accès aux documents administratifs en joignant la demande initiale, son justificatif d’envoi et la présente relance.",
    "Cordialement,"
]:
    doc.add_paragraph(para)
p = doc.add_paragraph()
r = p.add_run("Pièces à joindre à la CADA : ")
r.bold = True
p.add_run("demande initiale, preuve de réception, réponse de refus éventuelle, relance et description exacte des documents.")

doc.add_heading("Processus d’intégration dans Nos Deniers", level=1)
add_table(
    ["Contrôle", "Règle de validation"],
    [
        ["Dépôt brut", "Conserver le fichier original, son URL ou sa lettre de transmission et son empreinte SHA-256."],
        ["Identification", "Vérifier exercice, étape, AE ou CP, unité, périmètre budgétaire et date d’extraction."],
        ["Nomenclature", "Rattacher les codes publiés à l’année concernée ; conserver les changements de mission et de programme."],
        ["Rapprochement", "Comparer la somme aux totaux publiés ou à la restitution parente ; expliquer tout arrondi."],
        ["Blancs et zéros", "Un blanc reste indisponible. Seul un zéro explicitement publié devient une valeur nulle."],
        ["Traçabilité", "Associer chaque valeur à une source, une page ou une feuille et une ligne de preuve."],
        ["Publication", "Publier seulement après tests, audit d’empreinte et contrôle d’un exemple réel dans l’interface."],
    ],
    [4.1, 12.3],
)
p = doc.add_paragraph()
r = p.add_run("Règle spécifique aux gels. ")
r.bold = True
p.add_run("La réserve initiale, le surgel, le dégel et l’annulation sont des mouvements distincts. Le non-consommé en fin d’exercice ne permet jamais de déduire un gel.")

doc.add_heading("Ordre de priorité recommandé", level=1)
add_table(
    ["Priorité", "Travail", "Résultat recherché"],
    [
        ["1", "Achever la relecture des pages déjà présentes.", "Augmenter la couverture sans attendre une réponse externe."],
        ["2", "Envoyer la demande MaPrimeRénov’ 2020, 2025 et 2026.", "Obtenir les étapes et périmètres manquants du dossier pilote."],
        ["3", "Demander les restitutions de gels et mouvements aux ministères prioritaires.", "Compléter les données de gestion par programme."],
        ["4", "Demander la table de correspondance des nomenclatures 2017 à 2026.", "Fiabiliser les séries longues et les changements de périmètre."],
        ["5", "Étendre les demandes aux autres missions après validation du modèle.", "Industrialiser une procédure réutilisable pour tout le budget de l’État."],
    ],
    [2.0, 7.2, 7.2],
    aligns=["center", None, None],
)

h = doc.add_heading("Sources officielles utiles", level=1)
h.paragraph_format.page_break_before = True
sources = [
    ("Documentation budgétaire et circulaires", "https://www.budget.gouv.fr/documentation"),
    ("RAP 2025 par programme", "https://www.budget.gouv.fr/documentation/documents-budgetaires/exercice-2025/projet-loi-relatif-aux-resultats/budget-general"),
    ("Présentation des RAP", "https://www.budget.gouv.fr/reperes/loi_de_finances/articles/les-rap-ou-rapports-annuels"),
    ("AIFE et système Chorus", "https://aife.economie.gouv.fr/nos-applications/chorus-et-chorus-formulaire/"),
    ("Outils décisionnels Chorus", "https://aife.economie.gouv.fr/chorus-can/"),
    ("Accès aux documents administratifs des ministères économiques et financiers", "https://www.economie.gouv.fr/documentation/acces-aux-documents-administratifs"),
    ("Répertoire et contacts données du ministère de la Transition écologique", "https://www.ecologie.gouv.fr/repertoire-informations-publiques"),
    ("Formulaire de saisine du ministère de la Transition écologique", "https://contact.ecologie.gouv.fr/formulaire-de-saisine-de-l-administration-a6.html"),
    ("Code des relations entre le public et l’administration", "https://www.legifrance.gouv.fr/codes/section_lc/LEGITEXT000031366350/LEGISCTA000031367694/"),
    ("CADA modalités de communication", "https://www.cada.fr/administration/modalites-de-communication"),
    ("CADA rôle et saisine", "https://www.cada.fr/lacada/le-role-de-la-cada"),
    ("CADA extraction de fichiers informatiques", "https://www.cada.fr/particulier/le-document-est-il-administratif"),
    ("Article 57 de la LOLF", "https://www.legifrance.gouv.fr/loda/article_lc/LEGIARTI000044611996/2023-01-01"),
    ("Annonce officielle du budget MaPrimeRénov’ 2026", "https://www.ecologie.gouv.fr/presse/maprimerenov-reouverture-du-guichet-promulgation-loi-finances"),
]
for label, url in sources:
    p = doc.add_paragraph(style="List Bullet")
    add_hyperlink(p, label, url)

doc.add_heading("Décision proposée", level=1)
p = doc.add_paragraph()
p.add_run("Commencer immédiatement par la relecture des candidats déjà présents et envoyer en parallèle les deux demandes ciblées. ").bold = True
p.add_run("Le dossier MaPrimeRénov’ doit servir de test complet : une série ne devient disponible que lorsque le même montant peut être expliqué par son étape budgétaire, son programme porteur, son périmètre d’aide et sa preuve source. Une fois ce circuit validé, il pourra être appliqué à chaque mission et programme du budget de l’État.")

doc.core_properties.title = "Rendre disponibles les données encore manquantes dans Nos Deniers"
doc.core_properties.subject = "Mémo de collecte et de demandes administratives"
doc.core_properties.author = "LexMachine"
doc.core_properties.keywords = "budget de l'État, MaPrimeRénov, Chorus, gels, RAP, CADA"

doc.save(OUT)
print(OUT)
