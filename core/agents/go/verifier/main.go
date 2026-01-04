package main

import (
  "crypto/sha256"
  "encoding/hex"
  "encoding/json"
  "fmt"
  "io"
  "os"
  "path/filepath"
)

type RunManifest struct {
  Checksums map[string]string `json:"checksums"`
}

func shaFile(path string) (string, error) {
  f, err := os.Open(path)
  if err != nil { return "", err }
  defer f.Close()
  h := sha256.New()
  if _, err := io.Copy(h, f); err != nil { return "", err }
  return hex.EncodeToString(h.Sum(nil)), nil
}

func main() {
  if len(os.Args) != 2 {
    fmt.Println("usage: verifier <run_dir>")
    os.Exit(2)
  }
  runDir := os.Args[1]
  b, err := os.ReadFile(filepath.Join(runDir, "run.json"))
  if err != nil { fmt.Println("FAIL"); os.Exit(2) }
  var m RunManifest
  if err := json.Unmarshal(b, &m); err != nil { fmt.Println("FAIL"); os.Exit(2) }

  ok := true
  for rel, exp := range m.Checksums {
    got, err := shaFile(filepath.Join(runDir, rel))
    if err != nil || got != exp { ok = false }
  }
  if ok { fmt.Println("OK"); os.Exit(0) }
  fmt.Println("FAIL"); os.Exit(2)
}
