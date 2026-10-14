//! Independent file-inventory validation; never runs archived analysis code.
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

const MAX_FILE: u64 = 256 * 1024 * 1024;
const MAX_TOTAL: u64 = 1024 * 1024 * 1024;
const MAX_FILES: usize = 20_000;
type Result<T> = std::result::Result<T, String>;

struct Strict(Value);
struct StrictVisitor;
impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Strict;
    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str("strict JSON with unique object keys")
    }
    fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::Bool(v)))
    }
    fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::Number(v.into())))
    }
    fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Strict, E> {
        if v > i64::MAX as u64 {
            return Err(E::custom("large integer must be a string"));
        }
        Ok(Strict(Value::Number(Number::from(v))))
    }
    fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<Strict, E> {
        Err(E::custom("decimal values must be strings"))
    }
    fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::String(v.to_owned())))
    }
    fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::String(v)))
    }
    fn visit_none<E: de::Error>(self) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::Null))
    }
    fn visit_unit<E: de::Error>(self) -> std::result::Result<Strict, E> {
        Ok(Strict(Value::Null))
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> std::result::Result<Strict, A::Error> {
        let mut values = Vec::new();
        while let Some(Strict(value)) = seq.next_element()? {
            values.push(value);
        }
        Ok(Strict(Value::Array(values)))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> std::result::Result<Strict, A::Error> {
        let mut values = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON key: {key}")));
            }
            let Strict(value) = map.next_value()?;
            values.insert(key, value);
        }
        Ok(Strict(Value::Object(values)))
    }
}
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        d.deserialize_any(StrictVisitor)
    }
}

fn parse(data: &[u8]) -> Result<Value> {
    serde_json::from_slice::<Strict>(data)
        .map(|v| v.0)
        .map_err(|e| e.to_string())
}
fn object(value: &Value) -> Result<&Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| "expected JSON object".into())
}
fn text<'a>(object: &'a Map<String, Value>, key: &str) -> Result<&'a str> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing/invalid string: {key}"))
}
fn exact(object: &Map<String, Value>, keys: &[&str]) -> bool {
    object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key))
}
fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value.bytes().next().unwrap().is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn utc_timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() < 20
        || !bytes.is_ascii()
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || !value.ends_with('Z')
    {
        return false;
    }
    let number = |a: usize, b: usize| value[a..b].parse::<u32>().ok();
    let (Some(year), Some(month), Some(day), Some(hour), Some(minute), Some(second)) = (
        number(0, 4),
        number(5, 7),
        number(8, 10),
        number(11, 13),
        number(14, 16),
        number(17, 19),
    ) else {
        return false;
    };
    if year == 0 || month == 0 || month > 12 || hour > 23 || minute > 59 || second > 59 {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if day == 0 || day > days[(month - 1) as usize] {
        return false;
    }
    bytes.len() == 20
        || (bytes.len() > 21
            && bytes[19] == b'.'
            && bytes[20..bytes.len() - 1].iter().all(u8::is_ascii_digit))
}
fn safe_path(value: &str) -> bool {
    if value.is_empty()
        || value.len() > 1024
        || value.starts_with('/')
        || value.contains(['\\', ':'])
        || value.chars().any(|c| c < ' ')
    {
        return false;
    }
    value.split('/').all(|part| {
        if part.is_empty() || part == "." || part == ".." || part.ends_with(['.', ' ']) {
            return false;
        }
        let base = part.split('.').next().unwrap().to_ascii_uppercase();
        if ["CON", "PRN", "AUX", "NUL"].contains(&base.as_str()) {
            return false;
        }
        !(base.len() == 4
            && (base.starts_with("COM") || base.starts_with("LPT"))
            && (b'1'..=b'9').contains(&base.as_bytes()[3]))
    })
}
fn read(path: &Path) -> Result<Vec<u8>> {
    let file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut data = Vec::new();
    file.take(MAX_FILE + 1)
        .read_to_end(&mut data)
        .map_err(|e| e.to_string())?;
    if data.len() as u64 > MAX_FILE {
        return Err("file exceeds size limit".into());
    }
    Ok(data)
}
fn hash_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 1024 * 64];
    let mut total = 0u64;
    loop {
        let length = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if length == 0 {
            break;
        }
        total += length as u64;
        if total > MAX_FILE {
            return Err("file exceeds size limit".into());
        }
        hasher.update(&buffer[..length]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}
fn collect(
    root: &Path,
    directory: &Path,
    files: &mut BTreeMap<String, PathBuf>,
    aliases: &mut BTreeSet<String>,
    total: &mut u64,
) -> Result<()> {
    for entry in fs::read_dir(directory).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() {
            return Err("symbolic links are not artifacts".into());
        }
        if metadata.is_dir() {
            collect(root, &path, files, aliases, total)?;
            continue;
        }
        if !metadata.is_file() {
            return Err("nonregular artifact".into());
        }
        let relative = path
            .strip_prefix(root)
            .map_err(|e| e.to_string())?
            .components()
            .map(|component| {
                component
                    .as_os_str()
                    .to_str()
                    .map(str::to_owned)
                    .ok_or_else(|| "artifact path is not UTF-8".to_string())
            })
            .collect::<Result<Vec<_>>>()?
            .join("/");
        if !safe_path(&relative) {
            return Err("unsafe artifact path".into());
        }
        if !aliases.insert(relative.to_lowercase()) {
            return Err("duplicate artifact path".into());
        }
        *total += metadata.len();
        if metadata.len() > MAX_FILE || *total > MAX_TOTAL {
            return Err("file size limits exceeded".into());
        }
        files.insert(relative, path);
        if files.len() > MAX_FILES + 1 {
            return Err("file count limit exceeded".into());
        }
    }
    Ok(())
}

fn canonical(value: &Value, out: &mut String) -> Result<()> {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(v) => out.push_str(if *v { "true" } else { "false" }),
        Value::Number(v) => {
            if v.as_i64().is_none() {
                return Err("analysis decimals and large integers must be strings".into());
            }
            out.push_str(&v.to_string());
        }
        Value::String(v) => out.push_str(&serde_json::to_string(v).map_err(|e| e.to_string())?),
        Value::Array(values) => {
            out.push('[');
            for (index, v) in values.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                canonical(v, out)?;
            }
            out.push(']');
        }
        Value::Object(values) => {
            let mut keys: Vec<_> = values.keys().collect();
            keys.sort();
            out.push('{');
            for (index, key) in keys.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                out.push_str(&serde_json::to_string(key).map_err(|e| e.to_string())?);
                out.push(':');
                canonical(&values[*key], out)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

fn verify(root: &Path) -> Result<usize> {
    let metadata = fs::symlink_metadata(root).map_err(|e| e.to_string())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("root must be a regular directory".into());
    }
    let mut actual = BTreeMap::new();
    collect(root, root, &mut actual, &mut BTreeSet::new(), &mut 0)?;
    let manifest_path = actual
        .remove("manifest.json")
        .ok_or("manifest.json is missing")?;
    let manifest_value = parse(&read(&manifest_path)?)?;
    let manifest = object(&manifest_value)?;
    if !exact(
        manifest,
        &[
            "schema_version",
            "run_id",
            "case_id",
            "created_at",
            "analysis_digest",
            "files",
        ],
    ) {
        return Err("invalid manifest fields".into());
    }
    if text(manifest, "schema_version")? != "2.0"
        || !safe_id(text(manifest, "run_id")?)
        || !safe_id(text(manifest, "case_id")?)
        || !digest(text(manifest, "analysis_digest")?)
    {
        return Err("invalid manifest identity".into());
    }
    let created = text(manifest, "created_at")?;
    if !utc_timestamp(created) {
        return Err("timestamp must be UTC with Z".into());
    }
    let rows = manifest["files"]
        .as_array()
        .ok_or("files must be an array")?;
    if rows.is_empty() || rows.len() > MAX_FILES {
        return Err("inventory must be nonempty and bounded".into());
    }
    let mut seen = BTreeSet::new();
    let mut aliases = BTreeSet::new();
    let mut checked = 0;
    let mut engine = false;
    for row_value in rows {
        let row = object(row_value)?;
        if !exact(row, &["path", "sha256", "size_bytes"]) {
            return Err("invalid inventory entry".into());
        }
        let path = text(row, "path")?;
        let expected = text(row, "sha256")?;
        let size = row["size_bytes"].as_u64().ok_or("invalid file size")?;
        if !safe_path(path) || path == "manifest.json" || !digest(expected) || size > MAX_FILE {
            return Err("invalid inventory metadata".into());
        }
        if !aliases.insert(path.to_lowercase()) || !seen.insert(path.to_string()) {
            return Err("duplicate inventory path".into());
        }
        let file = actual
            .get(path)
            .ok_or_else(|| format!("missing artifact: {path}"))?;
        if fs::metadata(file).map_err(|e| e.to_string())?.len() != size {
            return Err(format!("size mismatch: {path}"));
        }
        if hash_file(file)? != expected {
            return Err(format!("checksum mismatch: {path}"));
        }
        checked += 1;
        if path.starts_with("engine/") {
            engine = true;
        }
    }
    if seen.len() != actual.len() {
        return Err("unlisted artifacts".into());
    }
    for name in [
        "case.json",
        "data/dataset.json",
        "analysis.json",
        "catalog.json",
        "environment.json",
    ] {
        if !seen.contains(name) {
            return Err(format!("mandatory artifact absent: {name}"));
        }
    }
    if !engine {
        return Err("engine snapshot absent".into());
    }
    let analysis = parse(&read(&actual["analysis.json"])?)?;
    object(&analysis)?;
    let mut normalized = String::new();
    canonical(&analysis, &mut normalized)?;
    normalized.push('\n');
    if format!("{:x}", Sha256::digest(normalized.as_bytes())) != text(manifest, "analysis_digest")?
    {
        return Err("analysis_digest mismatch".into());
    }
    let case_value = parse(&read(&actual["case.json"])?)?;
    if text(object(&case_value)?, "case_id")? != text(manifest, "case_id")? {
        return Err("case identity mismatch".into());
    }
    Ok(checked)
}

fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 2 {
        eprintln!("Usage: omphalos-integrity-verifier RUN_DIRECTORY");
        std::process::exit(2);
    }
    match verify(Path::new(&args[1])) {
        Ok(count) => println!(
            "OK: {count} file digests and normalized analysis verified; authenticity not assessed"
        ),
        Err(error) => {
            eprintln!("FAIL: {error}");
            std::process::exit(1);
        }
    }
}
