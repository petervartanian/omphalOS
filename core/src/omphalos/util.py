import hashlib, json
from pathlib import Path

def sha256_file(p):
 p=Path(p); h=hashlib.sha256();
 f=p.open('rb');
 [h.update(c) for c in iter(lambda:f.read(1024*1024), b'')];
 f.close();
 return h.hexdigest()

def write_json(p,o):
 p=Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(o,indent=2),encoding='utf-8')

def read_json(p):
 return json.loads(Path(p).read_text(encoding='utf-8'))
