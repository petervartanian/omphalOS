import argparse, sys
from .packs import pack_verify, pack_install
from .world import world_build
from .runner import run_case, verify_run
from .policy.gates import export_gate

def main(argv=None):
    p = argparse.ArgumentParser(prog="omphalos")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("pack", help="verify/install offline packs")
    sps = sp.add_subparsers(dest="pcmd", required=True)
    v = sps.add_parser("verify"); v.add_argument("index")
    i = sps.add_parser("install"); i.add_argument("index"); i.add_argument("--dest", default="core/assets/packs")

    wp = sub.add_parser("world", help="build world slice from recipe")
    wps = wp.add_subparsers(dest="wcmd", required=True)
    b = wps.add_parser("build"); b.add_argument("--profile", default="national"); b.add_argument("--out", default="hydrate/world")

    cp = sub.add_parser("case", help="run/verify a case")
    cps = cp.add_subparsers(dest="ccmd", required=True)
    r = cps.add_parser("run"); r.add_argument("case_path"); r.add_argument("--out", default="hydrate/runs")
    vr = cps.add_parser("verify"); vr.add_argument("run_path")

    ep = sub.add_parser("export", help="apply export gate to a packet")
    ep.add_argument("packet_json")

    a = p.parse_args(argv)

    if a.cmd == "pack":
        if a.pcmd == "verify":
            ok = pack_verify(a.index)
            print("OK" if ok else "FAIL")
            sys.exit(0 if ok else 2)
        if a.pcmd == "install":
            pack_install(a.index, a.dest)
            print("installed")
            return

    if a.cmd == "world":
        if a.wcmd == "build":
            world_build(a.profile, a.out)
            print("world built")
            return

    if a.cmd == "case":
        if a.ccmd == "run":
            print(run_case(a.case_path, a.out))
            return
        if a.ccmd == "verify":
            ok = verify_run(a.run_path)
            print("OK" if ok else "FAIL")
            sys.exit(0 if ok else 2)

    if a.cmd == "export":
        ok, report = export_gate(a.packet_json)
        print("OK" if ok else "DENY")
        if report:
            print(report)
        sys.exit(0 if ok else 2)

if __name__ == "__main__":
    main()
