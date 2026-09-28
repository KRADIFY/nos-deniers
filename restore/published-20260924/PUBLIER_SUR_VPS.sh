#!/bin/sh
set -eu
DIR=/home/marie/nos-deniers-update-20260924-final
if [ "$(id -u)" -ne 0 ]; then
  exec sudo /bin/sh "$DIR/PUBLIER_SUR_VPS.sh"
fi
python3 "$DIR/update.py"
python3 "$DIR/cleanup_previous.py"
printf '%s\n' 'Nos Deniers publié et ancienne version supprimée après vérification.'

