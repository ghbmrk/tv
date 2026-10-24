package wire

import (
	"bytes"
	"encoding/json"
	"io"
	"unicode/utf8"
)

func DecodeExact(data []byte, value any) bool {
	if !UniqueJSON(data) {
		return false
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if decoder.Decode(value) != nil {
		return false
	}
	if decoder.Decode(new(any)) != io.EOF {
		return false
	}
	// DisallowUnknownFields still accepts case-insensitive struct-field aliases.
	// Compare object keys against the typed encoding, recursively through arrays
	// and embedded structs. RawMessage boundaries remain opaque until their own
	// typed decode; missing fields are checked by each operation's contract.
	canonical, err := json.Marshal(value)
	if err != nil {
		return false
	}
	parse := func(data []byte) (any, error) {
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.UseNumber()
		var value any
		err := decoder.Decode(&value)
		return value, err
	}
	input, err := parse(data)
	if err != nil {
		return false
	}
	output, err := parse(canonical)
	if err != nil {
		return false
	}
	var exactKeys func(any, any) bool
	exactKeys = func(input, output any) bool {
		switch source := input.(type) {
		case map[string]any:
			target, ok := output.(map[string]any)
			if !ok {
				return false
			}
			for key, value := range source {
				other, ok := target[key]
				if !ok || !exactKeys(value, other) {
					return false
				}
			}
		case []any:
			target, ok := output.([]any)
			if !ok || len(source) != len(target) {
				return false
			}
			for i, value := range source {
				if !exactKeys(value, target[i]) {
					return false
				}
			}
		}
		return true
	}
	return exactKeys(input, output)
}

// Go's ordinary decoder permits duplicate object fields. A bounded token pass
// rejects ambiguity before typed decoding, including inside nested receipts.
func UniqueJSON(data []byte) bool {
	if len(data) == 0 || len(data) > 512*1024 || !utf8.Valid(data) {
		return false
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var walk func(int) bool
	walk = func(depth int) bool {
		if depth > 16 {
			return false
		}
		token, err := decoder.Token()
		if err != nil {
			return false
		}
		delimiter, container := token.(json.Delim)
		if !container {
			return true
		}
		switch delimiter {
		case '{':
			seen := map[string]bool{}
			for decoder.More() {
				key, err := decoder.Token()
				name, ok := key.(string)
				if err != nil || !ok || seen[name] || len(seen) >= 128 {
					return false
				}
				seen[name] = true
				if !walk(depth + 1) {
					return false
				}
			}
			end, err := decoder.Token()
			return err == nil && end == json.Delim('}')
		case '[':
			count := 0
			for decoder.More() {
				count++
				if count > 256 || !walk(depth+1) {
					return false
				}
			}
			end, err := decoder.Token()
			return err == nil && end == json.Delim(']')
		}
		return false
	}
	if !walk(0) {
		return false
	}
	_, err := decoder.Token()
	return err == io.EOF
}
