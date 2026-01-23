use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

mod sha256 {
    // Minimal SHA-256 implementation (FIPS 180-4).
    // Public domain style: no external dependencies.
    const K: [u32; 64] = [
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
    ];

    #[inline] fn rotr(x: u32, n: u32) -> u32 { (x >> n) | (x << (32 - n)) }
    #[inline] fn ch(x: u32, y: u32, z: u32) -> u32 { (x & y) ^ (!x & z) }
    #[inline] fn maj(x: u32, y: u32, z: u32) -> u32 { (x & y) ^ (x & z) ^ (y & z) }
    #[inline] fn big0(x: u32) -> u32 { rotr(x,2) ^ rotr(x,13) ^ rotr(x,22) }
    #[inline] fn big1(x: u32) -> u32 { rotr(x,6) ^ rotr(x,11) ^ rotr(x,25) }
    #[inline] fn sml0(x: u32) -> u32 { rotr(x,7) ^ rotr(x,18) ^ (x >> 3) }
    #[inline] fn sml1(x: u32) -> u32 { rotr(x,17) ^ rotr(x,19) ^ (x >> 10) }

    pub fn digest(data: &[u8]) -> [u8; 32] {
        let mut h: [u32; 8] = [
            0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
            0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19,
        ];

        // Pad
        let bit_len = (data.len() as u64) * 8;
        let mut msg = Vec::with_capacity(((data.len() + 9 + 63) / 64) * 64);
        msg.extend_from_slice(data);
        msg.push(0x80);
        while (msg.len() % 64) != 56 { msg.push(0); }
        msg.extend_from_slice(&bit_len.to_be_bytes());

        let mut w = [0u32; 64];

        for chunk in msg.chunks(64) {
            for i in 0..16 {
                let j = i * 4;
                w[i] = u32::from_be_bytes([chunk[j],chunk[j+1],chunk[j+2],chunk[j+3]]);
            }
            for i in 16..64 {
                w[i] = sml1(w[i-2]).wrapping_add(w[i-7]).wrapping_add(sml0(w[i-15])).wrapping_add(w[i-16]);
            }

            let mut a=h[0]; let mut b=h[1]; let mut c=h[2]; let mut d=h[3];
            let mut e=h[4]; let mut f=h[5]; let mut g=h[6]; let mut hh=h[7];

            for i in 0..64 {
                let t1 = hh.wrapping_add(big1(e)).wrapping_add(ch(e,f,g)).wrapping_add(K[i]).wrapping_add(w[i]);
                let t2 = big0(a).wrapping_add(maj(a,b,c));
                hh=g; g=f; f=e; e=d.wrapping_add(t1);
                d=c; c=b; b=a; a=t1.wrapping_add(t2);
            }

            h[0]=h[0].wrapping_add(a); h[1]=h[1].wrapping_add(b);
            h[2]=h[2].wrapping_add(c); h[3]=h[3].wrapping_add(d);
            h[4]=h[4].wrapping_add(e); h[5]=h[5].wrapping_add(f);
            h[6]=h[6].wrapping_add(g); h[7]=h[7].wrapping_add(hh);
        }

        let mut out = [0u8;32];
        for (i, v) in h.iter().enumerate() {
            out[i*4..i*4+4].copy_from_slice(&v.to_be_bytes());
        }
        out
    }

    pub fn hex(bytes: &[u8]) -> String {
        const HEX: &[u8;16] = b"0123456789abcdef";
        let mut s = String::with_capacity(bytes.len()*2);
        for &b in bytes {
            s.push(HEX[(b >> 4) as usize] as char);
            s.push(HEX[(b & 0x0f) as usize] as char);
        }
        s
    }
}

mod jsonmini {
    use std::collections::BTreeMap;

    #[derive(Debug, Clone)]
    pub enum J {
        Null,
        Bool(bool),
        Num(f64),
        Str(String),
        Arr(Vec<J>),
        Obj(BTreeMap<String, J>),
    }

    pub fn parse(input: &str) -> Result<J, String> {
        let mut p = Parser { s: input.as_bytes(), i: 0 };
        let v = p.value()?;
        p.ws();
        if p.i != p.s.len() { return Err("trailing_data".into()); }
        Ok(v)
    }

    struct Parser<'a> {
        s: &'a [u8],
        i: usize,
    }

    impl<'a> Parser<'a> {
        fn ws(&mut self) {
            while self.i < self.s.len() {
                match self.s[self.i] {
                    b' ' | b'\n' | b'\r' | b'\t' => self.i += 1,
                    _ => break,
                }
            }
        }

        fn peek(&self) -> Option<u8> {
            self.s.get(self.i).copied()
        }

        fn eat(&mut self, b: u8) -> Result<(), String> {
            if self.peek() == Some(b) { self.i += 1; Ok(()) } else { Err("unexpected_char".into()) }
        }

        fn value(&mut self) -> Result<J, String> {
            self.ws();
            match self.peek() {
                Some(b'n') => { self.lit(b"null")?; Ok(J::Null) }
                Some(b't') => { self.lit(b"true")?; Ok(J::Bool(true)) }
                Some(b'f') => { self.lit(b"false")?; Ok(J::Bool(false)) }
                Some(b'"') => Ok(J::Str(self.string()?)),
                Some(b'[') => self.array(),
                Some(b'{') => self.object(),
                Some(b'-') | Some(b'0'..=b'9') => Ok(J::Num(self.number()?)),
                _ => Err("expected_value".into()),
            }
        }

        fn lit(&mut self, t: &[u8]) -> Result<(), String> {
            if self.s.get(self.i..self.i+t.len()) == Some(t) {
                self.i += t.len(); Ok(())
            } else { Err("bad_literal".into()) }
        }

        fn string(&mut self) -> Result<String, String> {
            self.eat(b'"')?;
            let mut out = String::new();
            while self.i < self.s.len() {
                let c = self.s[self.i];
                self.i += 1;
                match c {
                    b'"' => return Ok(out),
                    b'\\' => {
                        let esc = self.peek().ok_or("bad_escape")?;
                        self.i += 1;
                        match esc {
                            b'"' => out.push('"'),
                            b'\\' => out.push('\\'),
                            b'/' => out.push('/'),
                            b'b' => out.push('\u{0008}'),
                            b'f' => out.push('\u{000c}'),
                            b'n' => out.push('\n'),
                            b'r' => out.push('\r'),
                            b't' => out.push('\t'),
                            b'u' => {
                                let hex = self.s.get(self.i..self.i+4).ok_or("bad_unicode")?;
                                self.i += 4;
                                let h = std::str::from_utf8(hex).map_err(|_| "bad_unicode")?;
                                let code = u16::from_str_radix(h, 16).map_err(|_| "bad_unicode")?;
                                out.push(char::from_u32(code as u32).ok_or("bad_unicode")?);
                            }
                            _ => return Err("bad_escape".into()),
                        }
                    }
                    _ => out.push(c as char),
                }
            }
            Err("unterminated_string".into())
        }

        fn number(&mut self) -> Result<f64, String> {
            let start = self.i;
            if self.peek() == Some(b'-') { self.i += 1; }
            while matches!(self.peek(), Some(b'0'..=b'9')) { self.i += 1; }
            if self.peek() == Some(b'.') {
                self.i += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) { self.i += 1; }
            }
            if matches!(self.peek(), Some(b'e') | Some(b'E')) {
                self.i += 1;
                if matches!(self.peek(), Some(b'+') | Some(b'-')) { self.i += 1; }
                while matches!(self.peek(), Some(b'0'..=b'9')) { self.i += 1; }
            }
            let s = std::str::from_utf8(&self.s[start..self.i]).map_err(|_| "bad_number")?;
            s.parse::<f64>().map_err(|_| "bad_number".into())
        }

        fn array(&mut self) -> Result<J, String> {
            self.eat(b'[')?;
            self.ws();
            let mut a = Vec::new();
            if self.peek() == Some(b']') { self.i += 1; return Ok(J::Arr(a)); }
            loop {
                a.push(self.value()?);
                self.ws();
                match self.peek() {
                    Some(b',') => { self.i += 1; }
                    Some(b']') => { self.i += 1; break; }
                    _ => return Err("bad_array".into()),
                }
            }
            Ok(J::Arr(a))
        }

        fn object(&mut self) -> Result<J, String> {
            self.eat(b'{')?;
            self.ws();
            let mut o = BTreeMap::new();
            if self.peek() == Some(b'}') { self.i += 1; return Ok(J::Obj(o)); }
            loop {
                self.ws();
                let k = self.string()?;
                self.ws();
                self.eat(b':')?;
                let v = self.value()?;
                o.insert(k, v);
                self.ws();
                match self.peek() {
                    Some(b',') => { self.i += 1; }
                    Some(b'}') => { self.i += 1; break; }
                    _ => return Err("bad_object".into()),
                }
            }
            Ok(J::Obj(o))
        }
    }
    pub fn as_obj(v: &J) -> Option<&BTreeMap<String, J>> { if let J::Obj(o)=v { Some(o) } else { None } }
    pub fn as_arr(v: &J) -> Option<&Vec<J>> { if let J::Arr(a)=v { Some(a) } else { None } }
    pub fn as_str(v: &J) -> Option<&str> { if let J::Str(s)=v { Some(s) } else { None } }
}

fn compute_sha256(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    Ok(sha256::hex(&sha256::digest(&bytes)))
}

fn die(msg: &str) -> ! {
    eprintln!("{}", msg);
    std::process::exit(1)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        die("Usage: omphalos-verifier <run_dir>");
    }
    let run_dir = PathBuf::from(&args[1]);

    let run_json = fs::read_to_string(run_dir.join("run.json")).map_err(|e| e.to_string());
    let run_json = match run_json { Ok(s) => s, Err(e) => die(&format!("read run.json: {}", e)) };
    let run_v = match jsonmini::parse(&run_json) { Ok(v) => v, Err(e) => die(&format!("parse run.json: {}", e)) };
    let run_o = jsonmini::as_obj(&run_v).unwrap_or_else(|| die("run.json not an object"));

    // schema_version check
    match run_o.get("schema_version").and_then(jsonmini::as_str) {
        Some("1.0") => {}
        _ => die("unsupported schema_version in run.json"),
    }

    let checks = run_o.get("checksums").and_then(jsonmini::as_obj).unwrap_or_else(|| die("checksums missing"));
    for (rel, expected_v) in checks {
        let expected = jsonmini::as_str(expected_v).unwrap_or("");
        let fp = run_dir.join(rel);
        let computed = compute_sha256(&fp).unwrap_or_else(|_| "".into());
        if computed != expected {
            die(&format!("checksum mismatch: {}", rel));
        }
    }

    let pkt_s = fs::read_to_string(run_dir.join("packet.json")).map_err(|e| e.to_string());
    let pkt_s = match pkt_s { Ok(s) => s, Err(e) => die(&format!("read packet.json: {}", e)) };
    let pkt_v = match jsonmini::parse(&pkt_s) { Ok(v) => v, Err(e) => die(&format!("parse packet.json: {}", e)) };
    let pkt_o = jsonmini::as_obj(&pkt_v).unwrap_or_else(|| die("packet.json not an object"));
    match pkt_o.get("schema_version").and_then(jsonmini::as_str) {
        Some("1.0") => {}
        _ => die("unsupported schema_version in packet.json"),
    }

    let claims = pkt_o.get("claims").and_then(jsonmini::as_arr).unwrap_or_else(|| die("claims missing"));
    if claims.is_empty() {
        die("claims empty");
    }
    for (i, c) in claims.iter().enumerate() {
        let co = jsonmini::as_obj(c).unwrap_or_else(|| die(&format!("claim {} invalid", i)));
        for k in ["evidence", "unknowns", "alternatives", "falsifiers"] {
            let arr = co.get(k).and_then(jsonmini::as_arr).unwrap_or_else(|| die(&format!("claim {} missing {}", i, k)));
            if arr.is_empty() {
                die(&format!("claim {} empty {}", i, k));
            }
        }
    }

    println!("OK");
}
