#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 && $(hostname) == vmi3304602 ]] || { echo 'Hôte ou utilisateur inattendu' >&2; exit 1; }
archive=/opt/nos-deniers/staging/20260929/tls-active.tar
config=/opt/nos-deniers/staging/20260929/nginx-budget-https.conf
site=/etc/nginx/sites-available/nos-deniers-budget
link=/etc/nginx/sites-enabled/nos-deniers-budget
test -f "$archive" && test -f "$config"
install -d -m 700 /etc/nginx/tls/nos-deniers
python3 - "$archive" <<'PYCODE'
import os, sys, tarfile
from pathlib import Path
archive=Path(sys.argv[1]); target=Path('/etc/nginx/tls/nos-deniers')
with tarfile.open(archive,'r:') as source:
    if sorted(source.getnames())!=['fullchain.pem','privkey.pem']:
        raise SystemExit('Entrées inattendues dans le certificat')
    for name,mode in [('fullchain.pem',0o644),('privkey.pem',0o600)]:
        member=source.getmember(name)
        if not member.isfile() or member.size>100000: raise SystemExit('Fichier TLS invalide')
        data=source.extractfile(member).read()
        temp=target/(name+'.new')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode)
        with os.fdopen(fd,'wb') as out: out.write(data)
        os.chmod(temp,mode)
        os.replace(temp,target/name)
PYCODE
openssl x509 -in /etc/nginx/tls/nos-deniers/fullchain.pem -noout -checkend 604800 >/dev/null
openssl x509 -in /etc/nginx/tls/nos-deniers/fullchain.pem -noout -ext subjectAltName | grep -F 'DNS:budget.lexmachine.net' >/dev/null
cmp <(openssl x509 -in /etc/nginx/tls/nos-deniers/fullchain.pem -pubkey -noout) <(openssl pkey -in /etc/nginx/tls/nos-deniers/privkey.pem -pubout) >/dev/null
install -d -m 755 /var/www/nos-deniers-acme
install -m 644 "$config" "$site"
ln -sfn "$site" "$link"
if ! nginx -t; then rm -f -- "$link"; echo 'Configuration Nginx invalide ; site Rock conservé' >&2; exit 1; fi
systemctl reload nginx
printf 'HTTPS de préproduction prêt pour budget.lexmachine.net ; DNS inchangé.\n'
