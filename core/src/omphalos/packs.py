import tarfile, shutil
from pathlib import Path
from .util import sha256_file, read_json

def pack_verify(index_path):
 idx=read_json(index_path); base=Path(index_path).parent; ok=True
 for pk in idx['packs']:
  p=base/pk['file']
  ok = ok and p.exists() and sha256_file(p)==pk['sha256']
 return ok

def pack_install(index_path, dest_dir):
 idx=read_json(index_path); base=Path(index_path).parent; dest=Path(dest_dir)
 dest.mkdir(parents=True, exist_ok=True)
 for pk in idx['packs']:
  src=base/pk['file']; out=dest/pk['name']
  if out.exists(): shutil.rmtree(out)
  out.mkdir(parents=True, exist_ok=True)
  with tarfile.open(src,'r:gz') as tf: tf.extractall(out)
