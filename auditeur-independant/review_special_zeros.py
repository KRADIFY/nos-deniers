import json,subprocess,shutil
from pathlib import Path
from review_document_zeros import lines,text,fragment,signature,groups,ROOT,OUT

data=json.loads(Path('document-zero-proofs.json').read_text('utf-8'));pending=json.loads(Path('resultats/document-zero-pending.json').read_text('utf-8'))
catalog={g['source']['id']:g['source'] for g in groups}
for f,_ in pending:
    s=catalog[f['source']];ws=json.loads((OUT/f"{s['id']}-{f['line']}.json").read_text('utf-8'));ls=lines(ws)
    p=dict(fact=signature(f),sha256=s['sha256'],source_url=s['url'],source_title=s['title'],reviewed_on='2026-09-28',kind='pdf',page=f['line'])
    fr=[];raw='0';status='source_zero'
    if f['year']==2017:
        heading=next(l for l in ls if 'PLR 2017' in text(l));program=next(l for l in ls if 'Programme n° '+f['program'] in text(l))
        row=next(l for l in ls if text(l).startswith('Total des CP ouverts '));nums=row[4:];assert all(w['text']=='0' for w in nums)
        fr=[fragment(heading,'exercise'),fragment(program,'program'),fragment(row[:4],'row'),fragment(nums,'value')]
        reason='Zéro imprimé sur la ligne « Total des CP ouverts » ; le haut de page identifie le programme et l’exercice 2017.'
    elif f['year']==2019:
        i=next(i for i,l in enumerate(ls) if text(l)=='(E1) (P1)');left=f['measure']=='AE'
        select=lambda l:[w for w in l if (w['xMin']<235 if left else w['xMin']>235)]
        val=select(ls[i+1]);assert text(val)=='0'
        header=select(ls[i-1]);assert text(header).startswith(f['measure']+' ouvert')
        program=next(l for l in ls if 'Programme n° '+f['program'] in text(l))
        fr=[fragment(program,'program'),fragment(header,'column'),fragment(select(ls[i]),'row'),fragment(val,'value')]
        # The printed schedule is explicitly HORS TITRE 2. Check the programme
        # source for its total all-titles recap before calling this a total.
        reason='Zéro imprimé dans le suivi des crédits, case '+('E1 (AE ouvertes)' if left else 'P1 (CP ouverts)')+'. Tableau hors titre 2 ; programme sans dépenses de personnel dans le RAP contrôlé.'
    elif f['stage']=='LFI':
        assert f['program']=='869' and f['year']==2018 and f['measure']=='CP'
        header=ls[25];assert text(header)=='LFI 2018 Recettes AE CP Solde'
        row=ls[37];assert text(row).startswith('Programme 869')
        val=[w for w in ls[39] if 360<w['xMin']<445];assert text(val)=='0'
        fr=[fragment(header,'exercise_and_columns'),fragment(row,'program'),fragment(val,'value')]
        reason='Zéro imprimé dans la colonne CP du programme 869, dans la section LFI 2018 du tableau du Sénat (la section PLF 2019 est distincte).'
    else:
        assert f['program']=='869' and f['year']==2018 and f['measure']=='CP'
        c=next(l for l in ls if text(l).startswith('Total des crédits consommés '));d=next(l for l in ls if text(l).startswith('Crédits ouverts - crédits consommés '))
        cv=[w for w in c if w['xMin']>520];dv=[w for w in d if w['xMin']>520];assert text(cv)==text(dv)=='0'
        fr=[fragment(ls[0],'exercise'),fragment(ls[3],'program'),fragment(ls[6],'measure_columns'),fragment(ls[7],'total_columns'),fragment(c[:4],'operand_1_label'),fragment(cv,'operand_1'),fragment(d[:5],'operand_2_label'),fragment(dv,'operand_2')]
        status='calculated_zero';raw='0 + 0 = 0'
        reason='La cellule « CP ouverts » est vide. Le zéro est établi par deux valeurs imprimées : CP consommés = 0 et CP ouverts − CP consommés = 0. Donc CP ouverts = 0 + 0. Le blanc seul ne constitue pas la preuve.'
    p.update(fragments=fr,status=status,raw=raw,reason=reason);data['proofs'].append(p)
Path('document-zero-proofs.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
print('Recorded',len(data['proofs']))
# Read the personnel-title context for the 2019 schedules (all five programmes).
for sid in sorted({f['source'] for f,_ in pending if f['year']==2019}):
    s=catalog[sid];dest=OUT/(sid+'-full.txt')
    subprocess.run([shutil.which('pdftotext'),'-layout',str(ROOT/s['path']),str(dest)],check=True,capture_output=True)
    tx=dest.read_text('utf-8');print('\n',sid)
    for l in tx.splitlines():
        if any(t in l.lower() for t in ('titre 2','personnel','récapitulation par action')):print(l.strip())
