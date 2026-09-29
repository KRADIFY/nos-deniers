#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Lancer avec sudo : sudo bash PROTEGER_AUDIT.sh" >&2
  exit 1
fi

NGINX_CONF=/etc/nginx/sites-available/auditnosdeniers.lexmachine.net
AUTH_FILE=/etc/nginx/.htpasswd-auditnosdeniers
BACKUP_DIR=/opt/nos-deniers-audit/backups/auth-$(date +%Y%m%d-%H%M%S)
USER_NAME=jcniquet

test -f "$NGINX_CONF"
command -v openssl >/dev/null
command -v nginx >/dev/null
read -r -s -p "Mot de passe pour $USER_NAME : " password
printf '\n'
read -r -s -p "Confirmer le mot de passe : " confirmation
printf '\n'
if [[ -z "$password" || "$password" != "$confirmation" ]]; then
  unset password confirmation
  echo "Mot de passe absent ou confirmation différente ; aucun changement." >&2
  exit 1
fi
password_hash=$(printf '%s\n' "$password" | openssl passwd -6 -stdin)
unset password confirmation

mkdir -p "$BACKUP_DIR"
cp -a "$NGINX_CONF" "$BACKUP_DIR/nginx.before"
if [[ -e "$AUTH_FILE" ]]; then cp -a "$AUTH_FILE" "$BACKUP_DIR/auth.before"; fi

tmp_auth=$(mktemp /etc/nginx/.htpasswd-auditnosdeniers.XXXXXX)
tmp_nginx=$(mktemp /etc/nginx/auditnosdeniers.XXXXXX)
cleanup() { rm -f "$tmp_auth" "$tmp_nginx"; }
trap cleanup EXIT
printf '%s:%s\n' "$USER_NAME" "$password_hash" > "$tmp_auth"
unset password_hash
chown root:www-data "$tmp_auth"
chmod 0640 "$tmp_auth"

python3 - "$NGINX_CONF" "$tmp_nginx" <<'PYCODE'
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text()
needle=" location / {\n  proxy_pass http://127.0.0.1:8554;"
auth="  auth_basic \"Audit Nos Deniers\";\n  auth_basic_user_file /etc/nginx/.htpasswd-auditnosdeniers;\n"
if source.count(needle)!=1:
    raise SystemExit("Bloc de l'auditeur inattendu : aucun fichier modifié.")
if "auth_basic_user_file /etc/nginx/.htpasswd-auditnosdeniers;" not in source:
    source=source.replace(needle, " location / {\n"+auth+"  proxy_pass http://127.0.0.1:8554;", 1)
Path(sys.argv[2]).write_text(source)
PYCODE

install -o root -g root -m 0644 "$tmp_nginx" "$NGINX_CONF"
install -o root -g www-data -m 0640 "$tmp_auth" "$AUTH_FILE"
if ! nginx -t; then
  cp -a "$BACKUP_DIR/nginx.before" "$NGINX_CONF"
  if [[ -e "$BACKUP_DIR/auth.before" ]]; then cp -a "$BACKUP_DIR/auth.before" "$AUTH_FILE"; else rm -f "$AUTH_FILE"; fi
  nginx -t
  echo "Configuration restaurée : validation Nginx échouée." >&2
  exit 1
fi
systemctl reload nginx
status=$(curl --silent --show-error --insecure --output /dev/null --write-out '%{http_code}' \
  --resolve auditnosdeniers.lexmachine.net:443:127.0.0.1 \
  https://auditnosdeniers.lexmachine.net/)
if [[ "$status" != 401 ]]; then
  cp -a "$BACKUP_DIR/nginx.before" "$NGINX_CONF"
  if [[ -e "$BACKUP_DIR/auth.before" ]]; then cp -a "$BACKUP_DIR/auth.before" "$AUTH_FILE"; else rm -f "$AUTH_FILE"; fi
  nginx -t && systemctl reload nginx
  echo "Configuration restaurée : accès sans mot de passe renvoie HTTP $status au lieu de 401." >&2
  exit 1
fi
echo "Auditeur protégé : une authentification est exigée avant tout accès."
echo "Aucun calcul d'audit n'a été démarré ; les rapports existants sont conservés."
