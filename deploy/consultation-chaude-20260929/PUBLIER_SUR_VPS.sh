#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec sudo python3 ./install.py "$@"
