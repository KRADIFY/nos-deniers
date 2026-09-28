from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'public/assets/explorer.js'
s=p.read_text(encoding='utf-8')
old='''const c=r.cells[k];return `<td title="${esc(c.reason)}">${euros(c.value)}</td>`;'''
new='''const c=r.cells[k];return `<td title="${esc(c.reason)}">${c.value===null?'<span class="missing-label">'+(c.status==='not_applicable'?'Sans objet':'Données non disponibles')+'</span>':euros(c.value)}</td>`;'''
assert s.count(old)==1
s=s.replace(old,new)
old='''<br><small>${esc(r.note)}</small></td></tr>`).join('');'''
new='''${(r.context_pages||[]).filter(p=>p!==r.page).map(p=>`<br><a href="/api/download/${esc(r.source)}#page=${p}" target="_blank" rel="noopener">Commentaire p. ${p} ↗</a>`).join('')}<br><small>${esc(r.note)}</small></td></tr>`).join('');'''
assert s.count(old)==1
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
p=root/'public/explorer.html';s=p.read_text(encoding='utf-8')
old='Première série : programme 174, Énergie, climat et après-mines, de 2017 à 2025.'
assert s.count(old)==1
s=s.replace(old,'Réserves des programmes de la mission Écologie, avec leurs tableaux sources.')
old='Dégels et annulations : signes tels que publiés. — : ligne absente ou ventilation indisponible. Les autres programmes et la part MaPrimeRénov’ restent à extraire ; aucun total de mission n’est calculé.'
assert s.count(old)==1
s=s.replace(old,'Dégels et annulations : signes tels que publiés. Les données absentes restent grisées. Les réserves sont présentées par programme, sans total de mission ni ventilation estimée pour MaPrimeRénov’.')
p.write_text(s,encoding='utf-8')
print('Reserve API and reserve panel updated; other views unchanged.')