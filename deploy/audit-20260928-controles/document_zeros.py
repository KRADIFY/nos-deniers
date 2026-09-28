"""Replay reviewed source coordinates. No inference from an empty PDF cell.

The registry is bound to the complete fact identity and original file SHA256.
Every run reads the actual source again; changed/missing context fails closed.
"""
import json,re,shutil,subprocess,xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

FIELDS=('source','year','budget','mission','program','action','subaction','stage','measure','category','title','line','field')
def fact_key(f):return tuple(f.get(k,'') for k in FIELDS)
def ordered(words):
    groups=[]
    for w in sorted(words,key=lambda w:((w['yMin']+w['yMax'])/2,w['xMin'])):
        cy=(w['yMin']+w['yMax'])/2
        if not groups or abs(cy-groups[-1][0])>2:groups.append((cy,[w]))
        else:groups[-1][1].append(w)
    return ' '.join(w['text'] for _,ws in groups for w in sorted(ws,key=lambda w:w['xMin']))

class Tables(HTMLParser):
    def __init__(self):super().__init__();self.tables=[];self.row=None;self.cell=None;self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth!=1:raise ValueError('Tableaux HTML imbriqués non pris en charge.')
            self.tables.append([])
        elif self.depth and tag=='tr':self.row=[];self.tables[-1].append(self.row)
        elif self.depth and tag in ('td','th'):
            if dict(attrs).get('rowspan','1')!='1' or dict(attrs).get('colspan','1')!='1':
                self.cell=['[cellule fusionnée] ']
            else:self.cell=[]
        elif tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if self.depth and tag in ('td','th'):
            if self.row is None or self.cell is None:raise ValueError('Cellule HTML hors ligne.')
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        elif tag=='table':self.depth-=1

class DocumentProofs:
    def __init__(self,registry=None):
        data=json.loads((Path(registry) if registry else Path(__file__).with_name('document-zero-proofs.json')).read_text('utf-8'))
        self.proofs={fact_key(p['fact']):p for p in data['proofs']};self.cache={}
        if len(self.proofs)!=len(data['proofs']):raise ValueError('Preuves documentaires en double.')
    def page(self,path,page):
        key=(str(path),page)
        if key not in self.cache:
            executable=shutil.which('pdftotext')
            if not executable:raise ValueError('Lecteur PDF pdftotext indisponible ; zéro non confirmé par cette exécution.')
            options={'creationflags':subprocess.CREATE_NO_WINDOW} if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
            result=subprocess.run([executable,'-f',str(page),'-l',str(page),'-bbox-layout',str(path),'-'],capture_output=True,check=True,timeout=45,**options)
            doc=ET.fromstring(result.stdout)
            self.cache[key]=[dict(text=w.text or '',**{k:float(v) for k,v in w.attrib.items()}) for w in doc.iter() if w.tag.endswith('}word')]
        return self.cache[key]
    def inspect(self,f,s,path):
        p=self.proofs.get(fact_key(f))
        if not p:return None
        # Caller verifies actual source bytes against this catalog SHA first.
        if p['sha256']!=s.get('sha256'):return dict(status='undetermined',reason='La preuve documentaire concerne une autre version du fichier.')
        try:
            if p['kind']=='html':
                key=(str(path),'html')
                if key not in self.cache:
                    parser=Tables();parser.feed(path.read_text('utf-8'));self.cache[key]=parser.tables
                table=self.cache[key][p['table']-1];row=table[p['row']-1]
                if table[0]!=p['header'] or row!=p['cells'] or row[p['column']-1]!='0':raise ValueError('En-tête, programme ou cellule HTML différent de la preuve relue.')
                location=dict(kind='html',table=p['table'],row=p['row'],columns=[p['column']])
            else:
                for part in p['fragments']:
                    words=self.page(path,part.get('page',p['page']));x1,y1,x2,y2=part['box']
                    selected=[w for w in words if x1<=(w['xMin']+w['xMax'])/2<=x2 and y1<=(w['yMin']+w['yMax'])/2<=y2]
                    actual=ordered(selected)
                    if actual!=part['text']:raise ValueError('Le contenu PDF relu ne correspond pas au repère contrôlé : '+part['role'])
                    if part['role'] in ('value','operand_1','operand_2') and (not actual.split() or any(t!='0' for t in actual.split())):
                        raise ValueError('Le repère numérique ne contient pas le zéro attendu.')
                roles={v['role'] for v in p['fragments']}
                required={'operand_1','operand_2'} if p['status']=='calculated_zero' else {'value'}
                if not required<=roles:raise ValueError('Preuve numérique incomplète.')
                location=dict(kind='pdf',page=p['page'],fragments=p['fragments'])
            return dict(status=p['status'],reason=p['reason'],raw=p['raw'],location=location,reviewed_on=p['reviewed_on'],source_sum='0')
        except Exception as e:return dict(status='undetermined',reason='Relecture documentaire non confirmée : '+str(e))
