package main

import (
  "crypto/sha256"
  "encoding/hex"
  "encoding/json"
  "errors"
  "flag"
  "io"
  "os"
  "path/filepath"
)

type Artifact struct {
  Path   string `json:"path"`
  Size   int64  `json:"size"`
  Sha256 string `json:"sha256"`
}

type Manifest struct {
  RunID            string    `json:"run_id"`
  ArtifactsRootHash string   `json:"artifacts_root_hash"`
  Artifacts        []Artifact `json:"artifacts"`
}

func sha256File(path string) (string, int64, error) {
  f, err := os.Open(path)
  if err != nil { return "", 0, err }
  defer f.Close()
  h := sha256.New()
  n, err := io.Copy(h, f)
  if err != nil { return "", 0, err }
  return hex.EncodeToString(h.Sum(nil)), n, nil
}

func readManifest(path string) (*Manifest, error) {
  b, err := os.ReadFile(path)
  if err != nil { return nil, err }
  var m Manifest
  if err := json.Unmarshal(b, &m); err != nil { return nil, err }
  return &m, nil
}

func verifyRun(runDir string) error {
  m, err := readManifest(filepath.Join(runDir, "manifest.json"))
  if err != nil { return err }
  if m.RunID == "" { return errors.New("missing run_id") }
  if len(m.Artifacts) == 0 { return errors.New("no artifacts declared") }
  for _, a := range m.Artifacts {
    p := filepath.Join(runDir, a.Path)
    gotHash, gotSize, err := sha256File(p)
    if err != nil { return err }
    if gotSize != a.Size { return errors.New("size mismatch: " + a.Path) }
    if gotHash != a.Sha256 { return errors.New("hash mismatch: " + a.Path) }
  }
  return nil
}

func main() {
  runDir := flag.String("run-dir", "", "run directory containing manifest.json")
  flag.Parse()
  if *runDir == "" {
    os.Stderr.WriteString("missing --run-dir\n")
    os.Exit(2)
  }
  if err := verifyRun(*runDir); err != nil {
    os.Stderr.WriteString(err.Error() + "\n")
    os.Exit(1)
  }
  os.Stdout.WriteString("ok\n")
}
