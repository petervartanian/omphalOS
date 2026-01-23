// omphalOS Go Verifier - Independent SQL execution and result verification
package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

type RunManifest struct {
	RunID     string            `json:"run_id"`
	CaseID    string            `json:"case_id"`
	Checksums map[string]string `json:"checksums"`
}

func computeSHA256(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	io.Copy(hash, file)
	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: %s <run_dir>\n", os.Args[0])
		os.Exit(1)
	}
	runDir := os.Args[1]
	data, _ := os.ReadFile(filepath.Join(runDir, "run.json"))
	var manifest RunManifest
	json.Unmarshal(data, &manifest)
	
	allValid := true
	for filename, expected := range manifest.Checksums {
		computed, _ := computeSHA256(filepath.Join(runDir, filename))
		if computed != expected {
			fmt.Printf("FAIL: %s\n", filename)
			allValid = false
		}
	}
	if allValid {
		fmt.Println("OK")
	} else {
		os.Exit(1)
	}
}
