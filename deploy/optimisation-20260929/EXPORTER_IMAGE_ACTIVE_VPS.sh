#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $(id -u) -ne 0 || $(hostname) != vmi3274092 ]]; then
  echo "Run as root on vmi3274092." >&2
  exit 1
fi

compose=/opt/lexmachine-budget/releases/20260929-historique76/compose.json
container=lexmachine-budget-public-web-1
archive=/home/marie/nos-deniers-web-20260929-active.tar
manifest=/home/marie/nos-deniers-web-20260929-active.txt
expected=$(python3 - "$compose" <<'PYCODE'
import json,sys
config=json.load(open(sys.argv[1]))
print(config['services']['web']['image'])
PYCODE
)
running_ref=$(docker inspect --format '{{.Config.Image}}' "$container")
running_id=$(docker inspect --format '{{.Image}}' "$container")
tag_id=$(docker image inspect --format '{{.Id}}' "$running_ref")

if [[ "$expected" != "$running_ref" || "$tag_id" != "$running_id" ]]; then
  echo "The running image does not match the active Compose image; export stopped." >&2
  printf 'compose=%s running=%s running_id=%s tag_id=%s\n' "$expected" "$running_ref" "$running_id" "$tag_id" >&2
  exit 1
fi

tmp="$archive.part.$$"
trap 'rm -f -- "$tmp"' EXIT
docker save -o "$tmp" "$running_ref"
sha=$(sha256sum "$tmp" | awk '{print $1}')
size=$(stat -c %s "$tmp")
mv -f -- "$tmp" "$archive"
chown marie:marie "$archive"
chmod 0600 "$archive"
{
  printf 'compose=%s\nrunning_ref=%s\nrunning_id=%s\narchive_size=%s\narchive_sha256=%s\n' "$expected" "$running_ref" "$running_id" "$size" "$sha"
  docker exec "$container" sha256sum /app/budget_service/api.py /app/budget_service/cell_reviews.py /app/budget_service/consultation.py /app/budget_service/web.py /app/public/assets/explorer.js /app/public/assets/explorer.css /app/public/explorer.html
  sha256sum /opt/lexmachine-budget/releases/20260929-historique76/data/derived/budget.sqlite
} > "$manifest"
chown marie:marie "$manifest"
chmod 0644 "$manifest"
printf 'Active web image exported: %s bytes, SHA-256 %s\n' "$size" "$sha"
printf 'Manifest: %s\n' "$manifest"

# Preserve the currently valid TLS certificate for a seamless HTTPS cutover.
# The key is never printed and the archive remains readable only by marie.
cert_dir=/etc/letsencrypt/live/budget.lexmachine.net
cert_archive=/home/marie/nos-deniers-tls-20260929-active.tar
cert_tmp="$cert_archive.part.$$"
trap 'rm -f -- "$tmp" "$cert_tmp"' EXIT
openssl x509 -in "$cert_dir/fullchain.pem" -noout -checkend 604800 >/dev/null
cmp <(openssl x509 -in "$cert_dir/fullchain.pem" -pubkey -noout) <(openssl pkey -in "$cert_dir/privkey.pem" -pubout) >/dev/null
tar -chf "$cert_tmp" -C "$cert_dir" fullchain.pem privkey.pem
mv -f -- "$cert_tmp" "$cert_archive"
chown marie:marie "$cert_archive"
chmod 0600 "$cert_archive"
cert_sha=$(sha256sum "$cert_archive" | awk '{print $1}')
printf 'tls_archive_size=%s\ntls_archive_sha256=%s\n' "$(stat -c %s "$cert_archive")" "$cert_sha" >> "$manifest"
printf 'TLS certificate archive exported and checked: %s\n' "$cert_archive"
