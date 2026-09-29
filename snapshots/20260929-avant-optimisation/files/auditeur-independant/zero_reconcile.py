"""Join source-zero observations to independently reread PDF cells."""
import collections,csv,json,sqlite3
from contextlib import closing
from pathlib import Path

from zeros import LABELS

CONFIRMED = 'documentary_zero'


def reconcile(out, coverage_dir):
    out, coverage_dir = Path(out), Path(coverage_dir)
    ledger = json.loads((out / 'zeros-sources.json').read_text('utf-8'))
    cells = json.loads((coverage_dir / 'cells.json').read_text('utf-8'))
    coverage = json.loads((coverage_dir / 'coverage.json').read_text('utf-8'))
    if coverage['documents_read'] != coverage['documents_expected']:
        raise ValueError('Relecture des PDF incomplète : aucun zéro reclassé.')
    proofs = collections.defaultdict(list)
    for cell in cells:
        if (cell['status'] != 'matched' or cell['expected_cents'] != 0
                or cell['actual_cents'] != [0] or not cell.get('sha256')
                or not cell.get('raw') or not cell.get('page')):
            continue
        key = (cell['source'], cell['sha256'], cell['budget'], cell['year'],
               cell['program'], cell['measure'], cell['stage'])
        proofs[key].append(cell)

    changed = 0
    for item in ledger['items']:
        if item['status'] != 'undetermined' or item.get('registry'):
            continue
        path = item['path'].split('/')
        if len(path) != 2:
            continue
        key = (item['source'], item.get('sha256'), item['budget'], item['year'],
               path[1], item['measure'], item['stage'])
        matches = proofs.get(key, [])
        if len(matches) != 1:
            continue
        cell = matches[0]
        item['source_reader_status'] = item['status']
        item['status'] = CONFIRMED
        item['label'] = LABELS[CONFIRMED]
        item['reason'] = ('Zéro imprimé dans le total du programme ; montant et case '
                          'rapprochés indépendamment de la base, PDF vérifié par empreinte.')
        item['location'] = dict(kind='pdf', page=cell['page'], bbox=cell['bbox'])
        item['documentary_proof'] = dict(source=cell['source'], sha256=cell['sha256'],
                                         year=cell['year'], program=cell['program'],
                                         measure=cell['measure'], stage=cell['stage'],
                                         page=cell['page'], raw=cell['raw'],
                                         expected_cents=0, actual_cents=0,
                                         coverage_reader_sha256=coverage['reader_sha256'],
                                         coverage_database_sha256=coverage['database_sha256'])
        changed += 1

    ledger['counts'] = dict(collections.Counter(i['status'] for i in ledger['items']))
    ledger['labels'] = LABELS
    ledger['reconciliation'] = dict(documentary_zeros_confirmed=changed,
                                    still_undetermined=ledger['counts'].get('undetermined', 0),
                                    scope='Six annexes PLR 2017–2022 relues ; autres documents non certifiés.')
    # The explorer uses SQLite, and the downloadable report uses JSON/CSV.
    with closing(sqlite3.connect(out / 'zeros-sources.sqlite')) as db, db:
        count = db.execute('select count(*) from items').fetchone()[0]
        if count != len(ledger['items']):
            raise ValueError('Registre SQLite et JSON des zéros désynchronisés.')
        db.executemany('update items set status=?, data=? where rowid=?',
                       [(item['status'], json.dumps(item, ensure_ascii=False), index)
                        for index, item in enumerate(ledger['items'], 1)
                        if item.get('source_reader_status') == 'undetermined'])
    tmp = out / 'zeros-sources.json.tmp'
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), 'utf-8')
    tmp.replace(out / 'zeros-sources.json')
    fields = ['budget','year','measure','stage','path','category','title','label','reason',
              'raw','line','field','source_title','source_url','source','sha256',
              'document_page','source_reader_status']
    tmp = out / 'zeros-sources.csv.tmp'
    with tmp.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(fields)
        for item in ledger['items']:
            values = [item.get(k, '') if k not in ('document_page',) else
                      item.get('documentary_proof', {}).get('page', '') for k in fields]
            writer.writerow(["'" + str(v) if str(v).lstrip().startswith(('=','+','-','@'))
                             else str(v) for v in values])
    tmp.replace(out / 'zeros-sources.csv')
    return ledger['reconciliation'] | dict(counts=ledger['counts'])
