"""The sole website change: a link to the independent auditor."""
URL='https://auditnosdeniers.lexmachine.net/'
LINK=' <a class="audit-link" href="'+URL+'" target="_blank" rel="noopener">Vérifier les chiffres <span aria-hidden="true">↗</span></a>\n'
CSS='\n/* Independent audit entry point. */\n.nav .audit-link{align-self:center;margin-left:auto;color:var(--blue);font-size:12px;font-weight:600;text-decoration:none;white-space:nowrap;padding:8px 12px;border:1px solid var(--line);border-radius:6px}.nav .audit-link:hover{text-decoration:underline}.nav .audit-link:focus-visible{outline:2px solid currentColor;outline-offset:3px}\n'
def patch(html,css):
    if 'class="audit-link"' not in html:
        start=html.index('<nav class="nav"');end=html.index('</nav>',start)
        html=html[:end]+LINK+html[end:]
    if '/* Independent audit entry point. */' not in css:css+=CSS
    return html,css
