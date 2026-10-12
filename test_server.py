"""Small HTTP integration check for real SQLite persistence and save conflicts."""
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from functools import partial
from pathlib import Path
from http.server import ThreadingHTTPServer
from app import Handler, initialize_database
from seed import create_seed

class QuietHandler(Handler):
    def log_message(self,*args): pass

class PersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.database=Path(cls.temp.name)/'test.sqlite3'
        initialize_database(cls.database)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,database=cls.database))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def request(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        con.request(method,path,body=body,headers=headers or {})
        r=con.getresponse();data=r.read();result=(r.status,data,{k.lower():v for k,v in r.getheaders()});con.close();return result

    def test_persistence_conflicts_origin_and_static_assets(self):
        code,body,_=self.request('GET','/api/state')
        self.assertEqual(code,200);self.assertIsNone(json.loads(body)['state'])
        state=create_seed()
        headers={'Content-Type':'application/json','X-Assurance-Client':'native-ui'}
        payload=json.dumps({'revision':0,'state':state})
        code,body,_=self.request('POST','/api/state',payload,headers)
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['revision'],1)
        code,body,_=self.request('GET','/api/state')
        self.assertEqual(json.loads(body)['state'],state)
        code,_,_=self.request('POST','/api/state',payload,headers)
        self.assertEqual(code,409)
        code,_,_=self.request('POST','/api/state',payload,{**headers,'Origin':'https://outside.example'})
        self.assertEqual(code,403)
        code,_,_=self.request('POST','/api/state',payload,{'Content-Type':'application/json'})
        self.assertEqual(code,403)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],1)
        for path,mime in [('/','text/html'),('/styles.css','text/css'),('/app.js','javascript'),('/engine.mjs','javascript'),('/seed.json','application/json'),('/index.html','text/html'),('/msg-logo.svg','image/svg+xml')]:
            code,body,headers=self.request('GET',path)
            self.assertEqual(code,200,path);self.assertIn(mime,headers['content-type']);self.assertGreater(len(body),100)
        code,_,_=self.request('GET','/../app.py')
        self.assertEqual(code,404)
        code,_,_=self.request('POST','/api/send-email','{}',{'Content-Type':'application/json'})
        self.assertEqual(code,404)
        config=json.loads((Path(__file__).parent/'dist/economic-example.json').read_text())
        config['n']=2000
        code,body,_=self.request('POST','/api/simulate',json.dumps(config),{'Content-Type':'application/json','X-Assurance-Client':'native-ui'})
        self.assertEqual(code,200,body)
        result=json.loads(body)
        self.assertEqual(result['reproducibility']['n'],2000)
        self.assertEqual(len(result['suppliers']),3)
        self.assertGreater(result['baseline']['mean']['mean'],0)
        code,_,_=self.request('POST','/api/simulate','{}',{'Content-Type':'application/json','X-Assurance-Client':'native-ui'})
        self.assertEqual(code,400)
        code,body,_=self.request('GET','/supplier-assurance-source.zip')
        self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIn('supplier-delivery-assurance/app.py',archive.namelist())
            self.assertIn('supplier-delivery-assurance/dist/msg-logo.svg',archive.namelist())
            self.assertIn('supplier-delivery-assurance/START_HERE.md',archive.namelist())
            self.assertFalse(any('.sqlite3' in p or '.openai' in p for p in archive.namelist()))

if __name__=='__main__':unittest.main()
