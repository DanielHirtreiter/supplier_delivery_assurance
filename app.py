"""Supplier assurance: native single-user Python + SQLite server.

Run: python app.py     Open: http://127.0.0.1:8000
"""
import argparse
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000

def source_archive():
    """Portable source only: no database, credentials or hosting identity."""
    files=['app.py','seed.py','README.md','START_HERE.md','.gitignore','test_server.py','test_engine.mjs',
           'dist/index.html','dist/styles.css','dist/app.js','dist/engine.mjs',
           'dist/icon.svg','dist/msg-logo.svg','dist/seed.json','dist/economics.js','dist/mc-worker.js',
           'dist/monte_carlo.py','dist/mc_core.py','requirements.txt','test_monte_carlo.py','MONTE_CARLO.md','dist/economic-example.json']
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(ROOT/name,'supplier-delivery-assurance/'+name)
    return stream.getvalue()

def initialize_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id = 1), revision INTEGER NOT NULL, body TEXT NOT NULL, updated_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS revisions (revision INTEGER PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL)')

def validate_state(state):
    if not isinstance(state, dict) or state.get('schema_version') != 1:
        raise ValueError('Unsupported workspace format.')
    for key in ('suppliers','lines','cases','messages','requests','audit'):
        if not isinstance(state.get(key), list):
            raise ValueError(f'{key} must be a list.')
    if len(state['lines']) > 10000 or len(state['messages']) > 20000:
        raise ValueError('Workspace is too large for this demonstration.')
    if not isinstance(state.get('settings'), dict):
        raise ValueError('Settings are required.')
    for collection in ('suppliers','lines','cases'):
        ids = [row.get('id') for row in state[collection] if isinstance(row,dict)]
        if len(ids) != len(state[collection]) or len(ids) != len(set(ids)) or None in ids:
            raise ValueError(f'{collection} must have unique IDs.')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, database, **kwargs):
        self.database = database
        super().__init__(*args, directory=str(ROOT/'dist'), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        super().end_headers()

    def json_response(self, code, data):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/state':
            with sqlite3.connect(self.database) as db:
                row=db.execute('SELECT revision,body FROM workspace WHERE id=1').fetchone()
            return self.json_response(200,dict(backend='python-sqlite',revision=row[0] if row else 0,state=json.loads(row[1]) if row else None))
        if path=='/api/health':
            return self.json_response(200,dict(status='ok',backend='python-sqlite'))
        if path=='/supplier-assurance-source.zip':
            body=source_archive()
            self.send_response(200)
            self.send_header('Content-Type','application/zip')
            self.send_header('Content-Disposition','attachment; filename="supplier-assurance-source.zip"')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path.startswith('/api/'):
            return self.json_response(404,dict(error='Unknown endpoint.'))
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path not in ('/api/state','/api/simulate'):
            return self.json_response(404,dict(error='Unknown endpoint.'))
        origin=self.headers.get('Origin')
        if (origin and urlsplit(origin).netloc!=self.headers.get('Host')) or self.headers.get('X-Assurance-Client')!='native-ui':
            return self.json_response(403,dict(error='Only same-origin workspace requests are accepted.'))
        if self.headers.get_content_type()!='application/json':
            return self.json_response(415,dict(error='JSON is required.'))
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY:
                return self.json_response(413,dict(error='Workspace must be smaller than 2 MB.'))
            payload=json.loads(self.rfile.read(length))
            if urlsplit(self.path).path=='/api/simulate':
                try:
                    import sys
                    if str(ROOT/'dist') not in sys.path: sys.path.insert(0,str(ROOT/'dist'))
                    from monte_carlo import run
                    result=run(payload)
                    return self.json_response(200,result)
                except ImportError:
                    return self.json_response(503,dict(error='Install simulation dependencies: python -m pip install -r requirements.txt'))
            validate_state(payload.get('state'))
            revision=payload.get('revision')
            if not isinstance(revision,int) or revision<0:
                raise ValueError('A valid revision is required.')
            body=json.dumps(payload['state'],ensure_ascii=False,separators=(',',':'))
            now=datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.database,timeout=10) as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT revision FROM workspace WHERE id=1').fetchone()
                actual=row[0] if row else 0
                if actual!=revision:
                    return self.json_response(409,dict(error='Another tab changed this workspace. Export your current session, then reload before saving.'))
                revision+=1
                db.execute('INSERT INTO revisions(revision,body,created_at) VALUES(?,?,?)',(revision,body,now))
                db.execute('INSERT INTO workspace(id,revision,body,updated_at) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,body=excluded.body,updated_at=excluded.updated_at',(revision,body,now))
            return self.json_response(200,dict(revision=revision,saved_at=now))
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            return self.json_response(400,dict(error=str(exc)))
        except sqlite3.Error:
            return self.json_response(503,dict(error='The local database is unavailable. Your unsaved form remains open.'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--database',type=Path,default=ROOT/'.runtime'/'assurance.sqlite3')
    args=parser.parse_args()
    initialize_database(args.database)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,database=args.database))
    print(f'Supplier Delivery Assurance: http://127.0.0.1:{args.port}',flush=True)
    print('Single-user demonstration. Data is synthetic; no SAP or mailbox connections.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__':main()
