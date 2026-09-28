"""Standalone audit service. No budget_service dependency, no writable budget mount."""
import hashlib,json,os,re,sqlite3,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zero_api import query as zero_query

ROOT=Path(__file__).resolve().parent
STATE=Path(os.environ.get('AUDIT_STATE_DIR','/audit-data'))
PUBLIC=os.environ.get('AUDIT_PUBLIC_URL','https://auditnosdeniers.lexmachine.net').rstrip('/')
lock=threading.Lock();process=None

def write(path,data):
    temp=Path(str(path)+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8');os.replace(temp,path)
def read(path,default=None):
    try:return json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):return default
def current():
    s=read(STATE/'service-state.json',{'status':'idle'})
    if s.get('status')=='running' and process is not None and process.poll() is not None:
        s.update(status='interrupted',message='Le processus a été interrompu. Les contrôles enregistrés sont conservés.');write(STATE/'service-state.json',s)
    rid=s.get('run_id')
    if rid and re.fullmatch(r'\d{8}-\d{6}-[a-f0-9]{6}',rid):
        folder=STATE/'runs'/rid
        progress=read(folder/'progress.json')
        if progress:s['progress']=progress
        report=read(folder/'rapport.json')
        if report:
            s['report']={k:report[k] for k in ('verdict','passed','counts','cases','error_count','limits','excluded_sections','zero_source_summary','zero_case_counts','summary','document_coverage','mutation_tests') if k in report}
            if (folder/'coverage/couverture.html').is_file():s['coverage_url']='/reports/'+rid+'/coverage/couverture.html'
            s['zeros_url']='/zeros?run='+rid
            s['report_url']='/reports/'+rid+'/rapport.html';s['json_url']='/reports/'+rid+'/rapport.json';s['csv_url']='/reports/'+rid+'/anomalies.csv'
        if s.get('status') in ('complete','interrupted','error') and (folder/'rapport.html').is_file():s['report_url']='/reports/'+rid+'/rapport.html'
    return s

def start(resume=False):
    global process
    with lock:
        if process is not None and process.poll() is None:return current(),202
        state=current()
        if state.get('status')=='running':return state,202
        if not resume and time.time()-state.get('started_unix',0)<int(os.environ.get('AUDIT_COOLDOWN_SECONDS','900')):
            state['message']='Un audit récent est disponible. Le prochain nouveau scan sera possible quinze minutes après le précédent lancement.'
            return state,429
        if resume and state.get('status')!='interrupted':return dict(error='Aucun audit interrompu à reprendre.'),409
        if resume:rid=state['run_id']
        else:
            rid=time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex()
            state=dict(run_id=rid,started_unix=time.time())
        folder=STATE/'runs'/rid;folder.mkdir(parents=True,exist_ok=True)
        state.update(status='running',message='Lecture de la base du serveur et préparation du contrôle.');write(STATE/'service-state.json',state)
        log=(folder/'worker.log').open('ab')
        args=[sys.executable,'-u',str(ROOT/'worker.py'),rid]
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        try:process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,**options)
        except Exception:
            state.update(status='error',message='Le processus de contrôle n’a pas pu démarrer.');write(STATE/'service-state.json',state);raise
        finally:log.close()
        return current(),202

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,value,status=200,kind='application/json; charset=utf-8',report=False):
        body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        headers={'Content-Type':kind,'Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'"+(" 'unsafe-inline'" if report else '')+"; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}
        for k,v in headers.items():self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/healthz':return self.reply(dict(service='nos-deniers-audit-independant',status='ok',read_only_reference=True))
        if path=='/api/status':return self.reply(current())
        if path=='/api/zeros':
            try:return self.reply(zero_query(STATE,urlsplit(self.path).query))
            except (ValueError,sqlite3.Error):return self.reply(dict(error='Relevé indisponible pour cette sélection.'),400)
        static={'/zeros':('zeros.html','text/html; charset=utf-8'),'/zeros.js':('zeros.js','text/javascript; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/memo':('memo.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path in static:
            name,kind=static[path];return self.reply((ROOT/'web'/name).read_bytes(),kind=kind)
        coverage_match=re.fullmatch(r'/reports/(\d{8}-\d{6}-[a-f0-9]{6})/coverage/(couverture\.html|couverture-cellules\.csv|catalogue-exploitation\.csv|coverage\.json|mutations\.json)',path)
        if coverage_match:
            p=STATE/'runs'/coverage_match[1]/'coverage'/coverage_match[2]
            if p.is_file():return self.reply(p.read_bytes(),kind={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.csv':'text/csv; charset=utf-8'}[p.suffix],report=True)
        match=re.fullmatch(r'/reports/(\d{8}-\d{6}-[a-f0-9]{6})/(rapport\.html|rapport\.json|anomalies\.csv|anomalies-techniques\.csv|zeros-sources\.csv|zeros-sources\.json|controle-affichage\.png)',path)
        if match:
            p=STATE/'runs'/match[1]/match[2]
            if p.is_file():return self.reply(p.read_bytes(),kind={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.csv':'text/csv; charset=utf-8','.png':'image/png'}[p.suffix],report=True)
        self.reply({'error':'Ressource introuvable'},404)
    def do_POST(self):
        if self.path!='/api/run':return self.reply({'error':'Route inconnue'},404)
        origin=self.headers.get('Origin')
        if origin and origin.rstrip('/')!=PUBLIC:return self.reply({'error':'Origine refusée'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply({'error':'JSON requis'},415)
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.reply({'error':'Taille invalide'},400)
        if not 0<length<=1024:return self.reply({'error':'Requête invalide'},400)
        try:
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict) or set(body)-{'resume'} or type(body.get('resume',False)) is not bool:raise ValueError()
            result,status=start(body.get('resume',False));return self.reply(result,status)
        except (ValueError,TypeError):return self.reply({'error':'Paramètres invalides'},400)
        except Exception:return self.reply({'error':'Audit non lancé. Consulter le journal de service.'},500)

def main():
    STATE.mkdir(parents=True,exist_ok=True)
    state=read(STATE/'service-state.json',{})
    if state.get('status')=='running':
        state.update(status='interrupted',message='Le service a redémarré. Les contrôles enregistrés peuvent être repris.');write(STATE/'service-state.json',state)
    ThreadingHTTPServer((os.environ.get('AUDIT_BIND','0.0.0.0'),int(os.environ.get('AUDIT_PORT','8095'))),Handler).serve_forever()
if __name__=='__main__':main()
