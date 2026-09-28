import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ.setdefault('BUDGET_DATA_DIR', str(root/'reports/integration-annexes-20260928/data'))
os.environ['BUDGET_PUBLIC_DIR']=str(root/'public')
from budget_service.web import Handler,ThreadingHTTPServer,api,download_path
from urllib.parse import urlsplit
import urllib.request,urllib.error,shutil
from contextlib import closing
# Preview only: reuse the published, unchanged document index while Docker is stopped.
class PreviewHandler(Handler):
    def do_GET(self):
        path=urlsplit(self.path).path
        remote=path in ('/api/document-search','/api/document-search/status','/api/semantic-search','/api/semantic-search/status') or path.startswith('/api/document-passage/')
        if path.startswith('/api/download/'):
            try:
                with closing(api.connect()) as db: record=api.source(db,path.rsplit('/',1)[-1])
                try: download_path(record)
                except LookupError: remote=True
            except (ValueError,LookupError): pass
        if remote:
            try:
                with urllib.request.urlopen('https://budget.lexmachine.net'+self.path,timeout=90) as r:
                    body=r.read()
                    return self.reply(body,kind=r.headers.get('Content-Type','application/octet-stream'),disposition=r.headers.get('Content-Disposition'))
            except urllib.error.HTTPError as e:return self.reply({'error':'Document public non disponible'},e.code)
            except Exception:return self.reply({'error':'Service documentaire public temporairement inaccessible'},503)
        return super().do_GET()
ThreadingHTTPServer(('127.0.0.1',8552),PreviewHandler).serve_forever()
