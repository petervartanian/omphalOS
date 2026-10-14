// Independent inventory verifier for omphalOS 2.0. It never executes evidence.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const maxFile = int64(256 * 1024 * 1024)
const maxTotal = int64(1024 * 1024 * 1024)
const maxFiles = 20000

var identifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$`)
var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var integerPattern = regexp.MustCompile(`^-?(0|[1-9][0-9]*)$`)

func validEscapes(data []byte) error {
	if !utf8.Valid(data) {
		return errors.New("JSON is not UTF-8")
	}
	inString := false
	for i := 0; i < len(data); i++ {
		if data[i] == '"' {
			inString = !inString
			continue
		}
		if !inString || data[i] != '\\' {
			continue
		}
		i++
		if i >= len(data) {
			return errors.New("invalid JSON escape")
		}
		if data[i] != 'u' {
			continue
		}
		if i+4 >= len(data) {
			return errors.New("invalid Unicode escape")
		}
		code, err := strconv.ParseUint(string(data[i+1:i+5]), 16, 16)
		if err != nil {
			return err
		}
		i += 4
		if code >= 0xD800 && code <= 0xDBFF {
			if i+6 >= len(data) || data[i+1] != '\\' || data[i+2] != 'u' {
				return errors.New("unpaired Unicode surrogate")
			}
			low, err := strconv.ParseUint(string(data[i+3:i+7]), 16, 16)
			if err != nil || low < 0xDC00 || low > 0xDFFF {
				return errors.New("unpaired Unicode surrogate")
			}
			i += 6
		} else if code >= 0xDC00 && code <= 0xDFFF {
			return errors.New("unpaired Unicode surrogate")
		}
	}
	return nil
}

func parseValue(d *json.Decoder, depth int) (any, error) {
	if depth > 128 {
		return nil, errors.New("JSON nesting limit exceeded")
	}
	token, err := d.Token()
	if err != nil {
		return nil, err
	}
	switch value := token.(type) {
	case json.Delim:
		if value == '{' {
			object := map[string]any{}
			for d.More() {
				keyToken, err := d.Token()
				if err != nil {
					return nil, err
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, errors.New("invalid object key")
				}
				if _, exists := object[key]; exists {
					return nil, fmt.Errorf("duplicate JSON key: %s", key)
				}
				child, err := parseValue(d, depth+1)
				if err != nil {
					return nil, err
				}
				object[key] = child
			}
			end, err := d.Token()
			if err != nil || end != json.Delim('}') {
				return nil, errors.New("invalid object")
			}
			return object, nil
		}
		if value == '[' {
			array := []any{}
			for d.More() {
				child, err := parseValue(d, depth+1)
				if err != nil {
					return nil, err
				}
				array = append(array, child)
			}
			end, err := d.Token()
			if err != nil || end != json.Delim(']') {
				return nil, errors.New("invalid array")
			}
			return array, nil
		}
		return nil, errors.New("unexpected JSON delimiter")
	default:
		return value, nil
	}
}

func parse(data []byte) (any, error) {
	if err := validEscapes(data); err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	value, err := parseValue(decoder, 0)
	if err != nil {
		return nil, err
	}
	if _, err := decoder.Token(); err != io.EOF {
		return nil, errors.New("trailing JSON content")
	}
	return value, nil
}

func quoted(value string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, ch := range value {
		switch ch {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if ch < 32 {
				fmt.Fprintf(&b, `\u%04x`, ch)
			} else {
				b.WriteRune(ch)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}

func canonical(value any) (string, error) {
	switch v := value.(type) {
	case nil:
		return "null", nil
	case bool:
		if v {
			return "true", nil
		}
		return "false", nil
	case string:
		return quoted(v), nil
	case json.Number:
		if !integerPattern.MatchString(string(v)) {
			return "", errors.New("analysis decimals must be strings")
		}
		number, err := strconv.ParseInt(string(v), 10, 64)
		if err != nil {
			return "", errors.New("analysis integers outside signed 64-bit range must be strings")
		}
		return strconv.FormatInt(number, 10), nil
	case []any:
		parts := []string{}
		for _, item := range v {
			text, err := canonical(item)
			if err != nil {
				return "", err
			}
			parts = append(parts, text)
		}
		return "[" + strings.Join(parts, ",") + "]", nil
	case map[string]any:
		keys := []string{}
		for key := range v {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		parts := []string{}
		for _, key := range keys {
			text, err := canonical(v[key])
			if err != nil {
				return "", err
			}
			parts = append(parts, quoted(key)+":"+text)
		}
		return "{" + strings.Join(parts, ",") + "}", nil
	}
	return "", errors.New("unsupported JSON value")
}

func safePath(value string) bool {
	if value == "" || len(value) > 1024 || strings.ContainsAny(value, "\\:") || strings.HasPrefix(value, "/") {
		return false
	}
	for _, ch := range value {
		if ch < 32 {
			return false
		}
	}
	for _, part := range strings.Split(value, "/") {
		if part == "" || part == "." || part == ".." || strings.HasSuffix(part, ".") || strings.HasSuffix(part, " ") {
			return false
		}
		base := strings.ToUpper(strings.Split(part, ".")[0])
		if base == "CON" || base == "PRN" || base == "AUX" || base == "NUL" {
			return false
		}
		if len(base) == 4 && (strings.HasPrefix(base, "COM") || strings.HasPrefix(base, "LPT")) && base[3] >= '1' && base[3] <= '9' {
			return false
		}
	}
	return true
}

func hashFile(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	h := sha256.New()
	_, err = io.Copy(h, io.LimitReader(file, maxFile+1))
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func read(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxFile+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > maxFile {
		return nil, errors.New("file size limit exceeded")
	}
	return data, nil
}

func exactKeys(object map[string]any, keys ...string) bool {
	if len(object) != len(keys) {
		return false
	}
	for _, key := range keys {
		if _, exists := object[key]; !exists {
			return false
		}
	}
	return true
}

func verify(root string) (int, error) {
	rootInfo, err := os.Lstat(root)
	if err != nil {
		return 0, err
	}
	if !rootInfo.IsDir() || rootInfo.Mode()&os.ModeSymlink != 0 {
		return 0, errors.New("root must be a regular directory")
	}
	actual := map[string]string{}
	aliases := map[string]bool{}
	total := int64(0)
	err = filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == root {
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return errors.New("symbolic links are not artifacts")
		}
		if info.IsDir() {
			return nil
		}
		if !info.Mode().IsRegular() {
			return errors.New("nonregular artifact")
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if !safePath(relative) {
			return errors.New("unsafe artifact path")
		}
		alias := strings.ToLower(relative)
		if aliases[alias] {
			return errors.New("duplicate artifact path")
		}
		aliases[alias] = true
		total += info.Size()
		if info.Size() > maxFile || total > maxTotal {
			return errors.New("file size limits exceeded")
		}
		actual[relative] = path
		if len(actual) > maxFiles+1 {
			return errors.New("file count limit exceeded")
		}
		return nil
	})
	if err != nil {
		return 0, err
	}
	data, err := read(actual["manifest.json"])
	if err != nil {
		return 0, err
	}
	value, err := parse(data)
	if err != nil {
		return 0, err
	}
	manifest, ok := value.(map[string]any)
	if !ok || !exactKeys(manifest, "schema_version", "run_id", "case_id", "created_at", "analysis_digest", "files") {
		return 0, errors.New("invalid manifest fields")
	}
	if manifest["schema_version"] != "2.0" {
		return 0, errors.New("unsupported schema")
	}
	runID, _ := manifest["run_id"].(string)
	caseID, _ := manifest["case_id"].(string)
	analysisDigest, _ := manifest["analysis_digest"].(string)
	created, _ := manifest["created_at"].(string)
	if !identifier.MatchString(runID) || !identifier.MatchString(caseID) || !digestPattern.MatchString(analysisDigest) || !strings.HasSuffix(created, "Z") {
		return 0, errors.New("invalid manifest identity")
	}
	if _, err := time.Parse(time.RFC3339Nano, created); err != nil {
		return 0, errors.New("invalid UTC timestamp")
	}
	rows, ok := manifest["files"].([]any)
	if !ok || len(rows) == 0 || len(rows) > maxFiles {
		return 0, errors.New("inventory must be nonempty and bounded")
	}
	delete(actual, "manifest.json")
	seen := map[string]bool{}
	listedAliases := map[string]bool{}
	engine := false
	checked := 0
	for _, item := range rows {
		row, ok := item.(map[string]any)
		if !ok || !exactKeys(row, "path", "sha256", "size_bytes") {
			return checked, errors.New("invalid inventory entry")
		}
		path, _ := row["path"].(string)
		digest, _ := row["sha256"].(string)
		number, ok := row["size_bytes"].(json.Number)
		size, err := strconv.ParseInt(string(number), 10, 64)
		if !safePath(path) || path == "manifest.json" || !digestPattern.MatchString(digest) || !ok || err != nil || size < 0 || size > maxFile {
			return checked, errors.New("invalid inventory metadata")
		}
		alias := strings.ToLower(path)
		if listedAliases[alias] {
			return checked, errors.New("duplicate inventory path")
		}
		listedAliases[alias] = true
		seen[path] = true
		file, exists := actual[path]
		if !exists {
			return checked, fmt.Errorf("missing artifact: %s", path)
		}
		info, err := os.Stat(file)
		if err != nil {
			return checked, err
		}
		if info.Size() != size {
			return checked, fmt.Errorf("size mismatch: %s", path)
		}
		hash, err := hashFile(file)
		if err != nil {
			return checked, err
		}
		if hash != digest {
			return checked, fmt.Errorf("checksum mismatch: %s", path)
		}
		checked++
		if strings.HasPrefix(path, "engine/") {
			engine = true
		}
	}
	if len(seen) != len(actual) {
		return checked, errors.New("unlisted artifacts")
	}
	for _, path := range []string{"case.json", "data/dataset.json", "analysis.json", "catalog.json", "environment.json"} {
		if !seen[path] {
			return checked, fmt.Errorf("mandatory artifact absent: %s", path)
		}
	}
	if !engine {
		return checked, errors.New("engine snapshot absent")
	}
	analysisBytes, err := read(actual["analysis.json"])
	if err != nil {
		return checked, err
	}
	analysis, err := parse(analysisBytes)
	if err != nil {
		return checked, err
	}
	if _, ok := analysis.(map[string]any); !ok {
		return checked, errors.New("analysis must be object")
	}
	normalized, err := canonical(analysis)
	if err != nil {
		return checked, err
	}
	computed := sha256.Sum256([]byte(normalized + "\n"))
	if hex.EncodeToString(computed[:]) != analysisDigest {
		return checked, errors.New("analysis_digest mismatch")
	}
	caseBytes, err := read(actual["case.json"])
	if err != nil {
		return checked, err
	}
	caseValue, err := parse(caseBytes)
	if err != nil {
		return checked, err
	}
	caseObject, ok := caseValue.(map[string]any)
	if !ok || caseObject["case_id"] != caseID {
		return checked, errors.New("case identity mismatch")
	}
	return checked, nil
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "Usage: omphalos-verify RUN_DIRECTORY")
		os.Exit(2)
	}
	checked, err := verify(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "FAIL: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("OK: %d file digests and normalized analysis verified; authenticity not assessed\n", checked)
}
