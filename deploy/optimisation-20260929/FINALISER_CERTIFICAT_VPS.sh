#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 && $(hostname) == vmi3304602 ]] || { echo 'Hôte ou utilisateur inattendu' >&2; exit 1; }

# Run only after the public A record points to this VPS. The copied certificate
# remains in service if issuance or validation fails.
resolved=$(getent ahostsv4 budget.lexmachine.net | awk 'NR==1 {print $1}')
[[ "$resolved" == 5.189.145.254 ]] || { echo "DNS pas encore basculé : $resolved" >&2; exit 1; }

certbot certonly --webroot -w /var/www/nos-deniers-acme \
  --cert-name budget.lexmachine.net -d budget.lexmachine.net \
  --non-interactive --agree-tos

site=/etc/nginx/sites-available/nos-deniers-budget
backup=$(mktemp /etc/nginx/sites-available/nos-deniers-budget.XXXXXX)
cp -- "$site" "$backup"
python3 - "$site" <<'PYCODE'
from pathlib import Path
import sys
site=Path(sys.argv[1]); config=site.read_text()
old='/etc/nginx/tls/nos-deniers/'
new='/etc/letsencrypt/live/budget.lexmachine.net/'
if config.count(old)!=2: raise SystemExit('Chemins TLS inattendus')
site.write_text(config.replace(old,new))
PYCODE
if ! nginx -t; then cp -- "$backup" "$site"; nginx -t; rm -f -- "$backup"; exit 1; fi
systemctl reload nginx
rm -f -- "$backup"
certbot renew --dry-run --cert-name budget.lexmachine.net
echo 'Certificat propre au nouveau VPS installé, renouvellement testé.'
