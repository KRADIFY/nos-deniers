import unittest
import json
from unittest.mock import patch
from budget_service.checks import corpus
from budget_service.checks import as_json,rpc_decode,CheckError,run_one
class ChecksTest(unittest.TestCase):
    def test_html_is_not_successful_json(self):
        with self.assertRaises(CheckError):as_json(b'<html>Access denied</html>')
    def test_sse_mcp_result(self):
        self.assertEqual(rpc_decode(b'event: message\ndata: {"jsonrpc":"2.0","result":{"tools":[]}}\n')["result"],{'tools':[]})
    def test_generic_error_does_not_disclose_credentials(self):
        def fail():raise ValueError('private-token-should-never-appear')
        result=run_one('test','test',fail)
        self.assertNotIn('private-token',str(result));self.assertEqual(result['status'],'blocked')
    def test_missing_credentials_are_blocked(self):
        def fail():raise FileNotFoundError('/private/secret')
        result=run_one('test','test',fail)
        self.assertEqual(result['status'],'blocked');self.assertNotIn('/private/secret',str(result))
class CorpusGuardTest(unittest.TestCase):
    def test_active_host_journal_prevents_database_read(self):
        guard={'checked_at_epoch':1000,'databases':{'ppl.db':{'exists':True,'active_journal':True}}}
        with patch('budget_service.checks.Path.read_bytes',return_value=json.dumps(guard).encode()), patch('budget_service.checks.time.time',return_value=1005), patch('budget_service.checks.sqlite3.connect') as connect:
            result=corpus('ppl.db')
            self.assertFalse(result['database_read']);connect.assert_not_called()
    def test_stale_guard_prevents_database_read(self):
        with patch('budget_service.checks.Path.read_bytes',return_value=b'{"checked_at_epoch":1000}'), patch('budget_service.checks.time.time',return_value=1201), patch('budget_service.checks.sqlite3.connect') as connect:
            with self.assertRaises(CheckError):corpus('ppl.db')
            connect.assert_not_called()
if __name__=='__main__':unittest.main()
