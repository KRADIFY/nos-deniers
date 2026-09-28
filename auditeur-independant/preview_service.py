"""Developer preview only. Does not launch an audit automatically."""
import os
from pathlib import Path
os.environ.update(AUDIT_STATE_DIR=str(Path('resultats/service-local').resolve()),AUDIT_PUBLIC_URL='http://127.0.0.1:8553',AUDIT_BIND='127.0.0.1',AUDIT_PORT='8553',
 AUDIT_DATABASE=str(Path('references/20260924-final/budget.sqlite').resolve()),AUDIT_REGISTRIES=str(Path('references/20260924-final/registries').resolve()),
 AUDIT_CORPUS_ROOT=str(Path('references/physical-sources').resolve()),
 AUDIT_NODE=str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'),AUDIT_QUICK_FOR_TEST='1')
import service
service.main()
