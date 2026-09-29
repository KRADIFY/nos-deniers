import json,os,signal,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import service
from test_service import ServiceTests

class StopTests(ServiceTests):
 def setUp(self):
  super().setUp();service.stopping=False
 def tearDown(self):
  if service.process is not None and service.process.poll() is None:
   service.process.kill();service.process.wait()
  service.stopping=False;super().tearDown()
 def state(self):
  rid='20260929-120000-abcdef';service.write(service.STATE/'service-state.json',dict(status='running',run_id=rid,started_unix=time.time()));return rid
 def test_stop_validation(self):
  headers={'Content-Type':'application/json','Origin':service.PUBLIC}
  for body in ({},{'run_id':'bad'},{'run_id':'20260929-120000-abcdef','pid':1}):self.assertEqual(self.request('/api/stop',body,headers)[0],400)
  self.assertEqual(self.request('/api/stop',{},dict(headers,Origin='https://example.org'))[0],403)
 def test_stale_stop_never_signals_new_worker(self):
  rid=self.state();child=Mock();child.poll.return_value=None;service.process=child
  with patch('service._signal_worker') as send:
   self.assertEqual(service.stop('20260929-120000-aaaaaa')[1],409);send.assert_not_called()
  child.poll.return_value=0
 def test_stop_is_idempotent_and_blocks_start(self):
  rid=self.state();child=Mock();child.poll.return_value=None;service.process=child
  with patch('service.threading.Thread') as thread,patch('service.subprocess.Popen') as launch:
   self.assertEqual(service.stop(rid)[1],202);self.assertEqual(service.stop(rid)[1],202)
   self.assertEqual(service.current()['status'],'stopping');self.assertEqual(service.start()[1],202)
   thread.assert_called_once();launch.assert_not_called()
  child.poll.return_value=0
 def test_finish_preserves_checkpoint_and_resume_id(self):
  rid=self.state();folder=service.STATE/'runs'/rid;folder.mkdir(parents=True);checkpoint=folder/'checkpoints.sqlite';checkpoint.write_bytes(b'previous results')
  child=Mock();child.poll.return_value=130;service.process=child;service.stopping=True
  with patch('service._signal_worker'):service._stop_worker(child,rid)
  self.assertEqual(service.current()['status'],'interrupted');self.assertEqual(checkpoint.read_bytes(),b'previous results')
  new=Mock();new.poll.return_value=None
  with patch('service.subprocess.Popen',return_value=new):state,code=service.start(True)
  self.assertEqual(code,202);self.assertEqual(state['run_id'],rid);new.poll.return_value=0
 def test_stop_timeout_escalates(self):
  rid=self.state();child=Mock();child.poll.return_value=-9;service.process=child;service.stopping=True
  child.wait.side_effect=[subprocess.TimeoutExpired('child',5),subprocess.TimeoutExpired('child',3),-9]
  with patch('service._signal_worker') as send:
   service._stop_worker(child,rid)
   self.assertGreaterEqual(send.call_count,3)
  self.assertEqual(service.current()['status'],'interrupted')
 @unittest.skipUnless(os.name=='posix','Isolated process-group test runs in Docker Linux')
 def test_real_blocked_worker_is_killed_and_checkpoint_kept(self):
  rid=self.state();marker=service.STATE/'checkpoint'
  code="import signal,time,pathlib;signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path("+repr(str(marker))+").write_text('saved');time.sleep(90)"
  child=subprocess.Popen([sys.executable,'-c',code],start_new_session=True);service.process=child
  for _ in range(100):
   if marker.exists():break
   time.sleep(.02)
  self.assertTrue(marker.exists());state,status=service.stop(rid);self.assertEqual(status,202)
  for _ in range(150):
   if not service.stopping:break
   time.sleep(.1)
  self.assertFalse(service.stopping);self.assertIsNotNone(child.poll());self.assertEqual(service.current()['status'],'interrupted');self.assertEqual(marker.read_text(),'saved')
if __name__=='__main__':unittest.main()
