#!/usr/bin/env bash
set -Eeuo pipefail
# Certbot runs deploy hooks only after a certificate was actually renewed.
case " ${RENEWED_DOMAINS:-} " in
  *' budget.lexmachine.net '*) nginx -t && systemctl reload nginx ;;
esac
