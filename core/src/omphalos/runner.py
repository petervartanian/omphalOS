import json, csv
from pathlib import Path
from datetime import datetime
from .warehouse import connect
from .util import sha256_file, write_json

def _import_csv(db, csv_path: Path, table: str):
    with csv_path.open('r',encoding='utf-8') as f:
        r=csv.reader(f); header=next(r)
        q=f"INSERT OR REPLACE INTO {table}({','.join(header)}) VALUES ({','.join(['?']*len(header))})"
        db.executemany(q, list(r)); db.commit()

def run_case(case_path, out_root='runs'):
    case=json.loads(Path(case_path).read_text(encoding='utf-8'))
    run_id=datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    run_dir=Path(out_root)/case['case_id']/run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path=run_dir/'warehouse.sqlite'
    db=connect(db_path)
    world=Path('hydrate/world')
    _import_csv(db, world/'shards'/'entities_000.csv', 'entities')
    _import_csv(db, world/'shards'/'shipments_000.csv', 'shipments')
    _import_csv(db, world/'shards'/'payments_000.csv', 'payments')
    cur=db.cursor()
    ship=cur.execute('SELECT COUNT(*) FROM shipments').fetchone()[0]
    pay=cur.execute('SELECT COUNT(*) FROM payments').fetchone()[0]
    packet={'case_id':case['case_id'],'run_id':run_id,'memo':f'Loaded {ship} shipments and {pay} payments.','annexes':{},'tables':[],'figures':[],'claims':[]}
    (run_dir/'packet.json').write_text(json.dumps(packet,indent=2),encoding='utf-8')
    manifest={'run_id':run_id,'case_id':case['case_id'],'created_utc':datetime.utcnow().isoformat()+'Z',
              'artifacts':{'warehouse':'warehouse.sqlite','packet':'packet.json'},
              'checksums':{'warehouse.sqlite':sha256_file(db_path),'packet.json':sha256_file(run_dir/'packet.json')}}
    write_json(run_dir/'run.json', manifest)
    db.close()
    return str(run_dir)

def verify_run(run_path):
    p=Path(run_path); m=json.loads((p/'run.json').read_text(encoding='utf-8'))
    ok=True
    for rel, exp in m['checksums'].items():
        fp=p/rel
        ok = ok and fp.exists() and sha256_file(fp)==exp
    return ok
