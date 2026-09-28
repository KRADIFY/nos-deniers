"""Isolated visual preview. Reuses the existing, read-only local API without copying data."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,unquote
import mimetypes,urllib.request,urllib.error,shutil

HERE=Path(__file__).resolve().parent
PUBLIC=HERE.parents[1]/'public'
UPSTREAM='http://127.0.0.1:8552'

class Handler(SimpleHTTPRequestHandler):
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        request=urlsplit(self.path)
        path=unquote(request.path)
        if path.startswith('/api/') or path in ('/healthz','/readyz'):
            try:
                with urllib.request.urlopen(UPSTREAM+request.path+('?' + request.query if request.query else ''),timeout=120) as response:
                    self.send_response(response.status)
                    for key in ('Content-Type','Content-Length','Content-Disposition','Content-Encoding'):
                        if response.headers.get(key):self.send_header(key,response.headers[key])
                    self.send_header('Cache-Control','no-store');self.end_headers()
                    if self.command!='HEAD':shutil.copyfileobj(response,self.wfile)
            except urllib.error.HTTPError as e:self.send_error(e.code)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
            except urllib.error.URLError:self.send_error(503,'Open the existing local Nos Deniers site first.')
            return
        if path=='/':file=HERE/'index.html'
        elif path=='/presentation.css':file=HERE/'presentation.css'
        elif path.startswith('/assets/'):
            file=(PUBLIC/path.lstrip('/')).resolve()
            if not file.is_relative_to(PUBLIC.resolve()):return self.send_error(404)
        else:return self.send_error(404)
        if not file.is_file():return self.send_error(404)
        kind=mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        if kind.startswith('text/') or file.suffix=='.js':kind+='; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(file.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers()
        if self.command!='HEAD':
            try:
                with file.open('rb') as stream:shutil.copyfileobj(stream,self.wfile)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

if __name__=='__main__':
    print('Nos Deniers — présentation : http://127.0.0.1:8556/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8556),Handler).serve_forever()
