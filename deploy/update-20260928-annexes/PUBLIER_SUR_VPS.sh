#!/bin/sh
set -eu
cd /home/marie/nos-deniers-update-20260928-annexes
exec sudo python3 ./install.py "$@"
