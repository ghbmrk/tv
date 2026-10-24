package native

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

const device = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
const document = `{"title":"PRIVATE-DOCUMENT-CANARY"}`

func digest(s string) string    { b := sha256.Sum256([]byte(s)); return hex.EncodeToString(b[:]) }
func raw(v any) json.RawMessage { b, _ := json.Marshal(v); return b }
