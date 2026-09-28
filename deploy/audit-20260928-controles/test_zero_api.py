from contextlib import closing
import json,sqlite3,tempfile,unittest
from pathlib import Path
from zero_api import query

class QueryTests(unittest.TestCase):
    def test_filter_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp);rid='20260928-130000-abcdef';folder=state/'runs'/rid;folder.mkdir(parents=True)
            with closing(sqlite3.connect(folder/'zeros-sources.sqlite')) as db, db:
                db.execute('create table items(status text, search text, data text)')
                db.execute('insert into items values(?,?,?)',('source_zero','2024 TA/174 CP',json.dumps({'path':'TA/174'})))
            result=query(state,'run='+rid+'&q=2024+174');self.assertEqual(result['count'],1)
            self.assertEqual(query(state,'run='+rid+'&q=%25')['count'],0)
            self.assertEqual(query(state,'run='+rid+"&status='+or+1=1--")['count'],0)
            with self.assertRaises(ValueError):query(state,'run=../../private')
            with self.assertRaises(ValueError):query(state,'run='+rid+'&kind=other')
if __name__=='__main__':unittest.main()
