//! omphalOS Rust Verifier Library
//! Cryptographic attestation and integrity verification

use anyhow::{Context, Result};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

#[derive(Debug, Deserialize)]
pub struct RunManifest {
    pub run_id: String,
    pub case_id: String,
    pub checksums: HashMap<String, String>,
}

pub fn compute_sha256(path: &Path) -> Result<String> {
    let contents = fs::read(path).context("Failed to read file")?;
    Ok(format!("{:x}", Sha256::digest(&contents)))
}

pub fn verify_run(run_dir: &Path) -> Result<bool> {
    let manifest_path = run_dir.join("run.json");
    let manifest_str = fs::read_to_string(&manifest_path)
        .context("Failed to read run.json")?;
    let manifest: RunManifest = serde_json::from_str(&manifest_str)
        .context("Failed to parse run.json")?;

    for (filename, expected_checksum) in &manifest.checksums {
        let file_path = run_dir.join(filename);
        let computed = compute_sha256(&file_path)
            .with_context(|| format!("Failed to hash {}", filename))?;

        if &computed != expected_checksum {
            eprintln!("Checksum mismatch: {}", filename);
            eprintln!("  Expected: {}", expected_checksum);
            eprintln!("  Computed: {}", computed);
            return Ok(false);
        }
    }

    Ok(true)
}
