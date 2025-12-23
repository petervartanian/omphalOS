use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{Read};
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
struct Artifact {
    path: String,
    size: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct Manifest {
    run_id: String,
    artifacts_root_hash: String,
    artifacts: Vec<Artifact>,
}

fn sha256_file(p: &Path) -> Result<(String, u64), String> {
    let mut f = File::open(p).map_err(|e| format!("open {}: {}", p.display(), e))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    let mut total: u64 = 0;
    loop {
        let n = f.read(&mut buf).map_err(|e| format!("read {}: {}", p.display(), e))?;
        if n == 0 { break; }
        total += n as u64;
        hasher.update(&buf[..n]);
    }
    let hash = hex::encode(hasher.finalize());
    Ok((hash, total))
}

fn read_manifest(run_dir: &Path) -> Result<Manifest, String> {
    let p = run_dir.join("manifest.json");
    let bytes = std::fs::read(&p).map_err(|e| format!("read {}: {}", p.display(), e))?;
    serde_json::from_slice(&bytes).map_err(|e| format!("parse manifest: {}", e))
}

fn verify_run(run_dir: &Path) -> Result<(), String> {
    let m = read_manifest(run_dir)?;
    if m.run_id.is_empty() { return Err("missing run_id".to_string()); }
    if m.artifacts.is_empty() { return Err("no artifacts declared".to_string()); }
    for a in m.artifacts {
        let p = run_dir.join(&a.path);
        let (hash, size) = sha256_file(&p)?;
        if size != a.size { return Err(format!("size mismatch: {}", a.path)); }
        if hash != a.sha256 { return Err(format!("hash mismatch: {}", a.path)); }
    }
    Ok(())
}

fn main() {
    let mut args = std::env::args().skip(1);
    let mut run_dir: Option<PathBuf> = None;
    while let Some(a) = args.next() {
        if a == "--run-dir" {
            run_dir = args.next().map(PathBuf::from);
        }
    }
    let dir = match run_dir {
        Some(d) => d,
        None => {
            eprintln!("missing --run-dir");
            std::process::exit(2);
        }
    };
    if let Err(e) = verify_run(&dir) {
        eprintln!("{}", e);
        std::process::exit(1);
    }
    println!("ok");
}
