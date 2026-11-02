import unittest, threading, http.client, json, os, secrets, time
from pathlib import Path
from unittest.mock import patch
import app

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=secrets.token_urlsafe(32);os.environ['API_KEY']=cls.key
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.port=cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
    def setUp(self):app.JOBS.clear()
    def call(self,method,path,data=None,auth=True):
        c=http.client.HTTPConnection('127.0.0.1',self.port)
        h={'Content-Type':'application/json'}
        if auth:h['Authorization']='Bearer '+self.key
        c.request(method,path,json.dumps(data).encode() if data else None,h)
        r=c.getresponse();body=r.read();result=(r.status,dict(r.getheaders()),body);c.close();return result
    def test_no_key_denied(self):
        self.assertEqual(self.call('POST','/jobs',{'url':'https://youtube.com/watch?v=x'},False)[0],401)
    def test_internal_and_lookalike_denied(self):
        for url in ['http://localhost/','http://127.0.0.1/','https://youtube.com.evil.example/','file:///etc/passwd','https://youtube.com:444/','https://name:secret@youtube.com/']:
            self.assertEqual(self.call('POST','/jobs',{'url':url})[0],400)
    def test_single_job_and_ticket_download(self):
        with patch.object(app.POOL,'submit'):
            status,_,raw=self.call('POST','/jobs',{'url':'https://www.youtube.com/watch?v=123'})
            self.assertEqual(status,202);job=json.loads(raw)
            self.assertEqual(self.call('POST','/jobs',{'url':'https://vimeo.com/123'})[0],429)
            self.assertEqual(self.call('GET','/jobs/'+job['id']+'?ticket=wrong')[0],403)
            d=app.ROOT/job['id'];d.mkdir();f=d/'tai-tat.mp4';f.write_bytes(b'fake-mp4-for-protocol-test')
            app.JOBS[job['id']].update(state='done',file=str(f),name=f.name,size=f.stat().st_size)
            status,headers,body=self.call('GET','/download/'+job['id']+'?ticket='+job['ticket'])
            self.assertEqual(status,200);self.assertEqual(body,f.read_bytes());self.assertIn('attachment',headers['Content-Disposition'])
            self.assertEqual(self.call('GET','/download/'+job['id']+'?ticket='+job['ticket'],auth=False)[0],401)
            app.JOBS[job['id']]['created']=time.time()-1000;app.cleanup();self.assertFalse(f.exists())
    def test_health_works_without_key(self):
        self.assertEqual(self.call('GET','/health',auth=False)[0],200)
if __name__=='__main__':unittest.main()
