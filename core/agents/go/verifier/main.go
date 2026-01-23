// omphalOS Go Verifier (v1.0)
// Independent integrity and admissibility witness.
//
// Scope (honest):
//   - recompute SHA-256 checksums from run.json
//   - parse packet.json and ensure mandatory doubt-structure is present
//
// This verifier is intentionally small and dependency-free.
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
	SchemaVersion string            `json:"schema_version"`
	RunID         string            `json:"run_id"`
	CaseID        string            `json:"case_id"`
	Checksums     map[string]string `json:"checksums"`
}

type Packet struct {
	SchemaVersion string        `json:"schema_version"`
	CaseID        string        `json:"case_id"`
	RunID         string        `json:"run_id"`
	Memo          string        `json:"memo"`
	Claims        []interface{} `json:"claims"`
}

func computeSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	_, _ = io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), nil
}

func die(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	os.Exit(1)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: %s <run_dir>\n", os.Args[0])
		os.Exit(1)
	}
	runDir := os.Args[1]

	manifestBytes, err := os.ReadFile(filepath.Join(runDir, "run.json"))
	if err != nil {
		die("read run.json: " + err.Error())
	}
	var manifest RunManifest
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		die("parse run.json: " + err.Error())
	}
	if manifest.SchemaVersion != "1.0" {
		die("unsupported schema_version in run.json")
	}

	// Integrity: recompute checksums.
	allValid := true
	for filename, expected := range manifest.Checksums {
		computed, err := computeSHA256(filepath.Join(runDir, filename))
		if err != nil || computed != expected {
			fmt.Printf("FAIL: %s\n", filename)
			allValid = false
		}
	}
	if !allValid {
		os.Exit(1)
	}

	// Admissibility: packet must contain mandatory doubt structure.
	packetBytes, err := os.ReadFile(filepath.Join(runDir, "packet.json"))
	if err != nil {
		die("read packet.json: " + err.Error())
	}

	var pkt map[string]interface{}
	if err := json.Unmarshal(packetBytes, &pkt); err != nil {
		die("parse packet.json: " + err.Error())
	}
	if pkt["schema_version"] != "1.0" {
		die("unsupported schema_version in packet.json")
	}

	claims, ok := pkt["claims"].([]interface{})
	if !ok || len(claims) == 0 {
		die("claims missing or empty")
	}
	for i, c := range claims {
		obj, ok := c.(map[string]interface{})
		if !ok {
			die(fmt.Sprintf("claim %d invalid", i))
		}
		for _, k := range []string{"evidence", "unknowns", "alternatives", "falsifiers"} {
			v, ok := obj[k].([]interface{})
			if !ok || len(v) == 0 {
				die(fmt.Sprintf("claim %d missing or empty: %s", i, k))
			}
		}
	}

	fmt.Println("OK")
}
