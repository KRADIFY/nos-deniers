import tempfile
import unittest
from pathlib import Path
from budget_service.data_signature import signature


class DataSignatureTests(unittest.TestCase):
    def test_changed_database_or_registry_invalidates_same_date_certificate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);db=root/'budget.sqlite';reg=root/'registries';reg.mkdir()
            db.write_bytes(b'first database');table=reg/'movements.json';table.write_text('{"amount":10}')
            before=signature(db,reg)
            self.assertEqual(before,signature(db,reg))
            table.write_text('{"amount":11}')
            modified=signature(db,reg)
            self.assertNotEqual(before,modified)
            self.assertEqual(before['database_sha256'],modified['database_sha256'])
            db.write_bytes(b'other database')
            self.assertNotEqual(modified['database_sha256'],signature(db,reg)['database_sha256'])

if __name__=='__main__':unittest.main()
