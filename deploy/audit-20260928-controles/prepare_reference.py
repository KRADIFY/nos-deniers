"""Create a separate immutable input snapshot; never modifies source files."""
import argparse,datetime,json,os,shutil,sqlite3,subprocess,tempfile
from pathlib import Path
from oracle import digest

def prepare(database,registries,output):
    database=Path(database).resolve();registries=Path(registries).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Choisir un nouveau dossier : une référence existante ne doit pas être écrasée.')
    output.mkdir(parents=True);(output/'registries').mkdir()
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(output/'budget.sqlite') as dst:src.backup(dst)
    for p in registries.glob('*.json'):shutil.copy2(p,output/'registries'/p.name)
    with sqlite3.connect((output/'budget.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        meta={k:json.loads(v) for k,v in db.execute('select * from meta')}
        count=db.execute('select count(*) from facts').fetchone()[0]
    manifest=dict(created_at=datetime.datetime.now().astimezone().isoformat(),origin_database=str(database),
      data_version=meta.get('data_version'),fact_count=count,
      scope='Référence structurée. Aucun nouveau contrôle documentaire exhaustif implicite.',
      files={p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(reference=str(output),facts=count,data_version=meta.get('data_version')),ensure_ascii=False))
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path);p.add_argument('--registries',type=Path)
    p.add_argument('--docker',help='Conteneur local à lire avec docker cp, sans exécuter le code du site')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--select',action='store_true')
    a=p.parse_args()
    if a.docker:
        with tempfile.TemporaryDirectory(prefix='nos-deniers-reference-') as t:
            d=Path(t)
            for remote,local in [('/data/derived/budget.sqlite',d/'budget.sqlite'),('/app/budget_service/data',d/'registries')]:
                subprocess.run(['docker','cp',a.docker+':'+remote,str(local)],check=True,capture_output=True)
            result=prepare(d/'budget.sqlite',d/'registries',a.output)
    else:
        if not a.database or not a.registries:p.error('--database et --registries, ou --docker, sont requis')
        result=prepare(a.database,a.registries,a.output)
    if a.select:
        (Path(__file__).parent/'reference-selection.json').write_text(json.dumps({'path':str(result)},ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':main()
