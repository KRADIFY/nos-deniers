import json,socket,unittest
from unittest.mock import patch
import install

class InstallPortTests(unittest.TestCase):
    def test_available_port(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        with patch('install.AUDIT_PORT',port),patch('install.capture') as capture:
            install.check_audit_port();capture.assert_not_called()
    def test_occupied_port_refuses_unrelated_service(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));probe.listen();port=probe.getsockname()[1]
            with patch('install.AUDIT_PORT',port),patch('install.capture',return_value='[]'):
                with self.assertRaisesRegex(RuntimeError,'Aucun service modifié'):install.check_audit_port()
    def test_repeat_install_accepts_only_own_running_mapping(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));probe.listen();port=probe.getsockname()[1]
            info=dict(State={'Running':True},Config={'Labels':{'com.docker.compose.project':'nos-deniers-audit','com.docker.compose.service':'audit'}},NetworkSettings={'Ports':{'8095/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]}})
            with patch('install.AUDIT_PORT',port),patch('install.capture',return_value=json.dumps([info])):install.check_audit_port()
            info['Config']['Labels']['com.docker.compose.project']='unrelated'
            with patch('install.AUDIT_PORT',port),patch('install.capture',return_value=json.dumps([info])):
                with self.assertRaises(RuntimeError):install.check_audit_port()
    def test_nginx_uses_same_new_port_for_http_and_https(self):
        for tls in (False,True):
            config=install.nginx_config(tls)
            self.assertIn('proxy_pass http://127.0.0.1:8554;',config)
            self.assertNotIn('8553',config)
if __name__=='__main__':unittest.main()
