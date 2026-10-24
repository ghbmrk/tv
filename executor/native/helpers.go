// Package native implements the paired TV protocol without a broker dependency.
package native

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"github.com/ghbmrk/tv/executor/internal/wire"
	"regexp"
	"time"
)

const maxExactInteger int64 = 9007199254740991

var hexDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)

type Response struct {
	Status string
	Result json.RawMessage
}
type Transport interface {
	DeviceID() string
	Request(context.Context, string, map[string]any, int64) (Response, error)
}
type Receipt struct {
	RequestID        string `json:"request_id"`
	Revision         int64  `json:"revision"`
	PreviousRevision int64  `json:"previous_revision"`
	DocumentSHA256   string `json:"document_sha256"`
	OperationSHA256  string `json:"operation_sha256"`
}

func hash(text string) string { sum := sha256.Sum256([]byte(text)); return hex.EncodeToString(sum[:]) }
func expiry(ctx context.Context) int64 {
	until := time.Now().Add(10 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(until) {
		until = d
	}
	return until.UnixMilli()
}
func decodeExact(data []byte, v any) bool { return wire.DecodeExact(data, v) }
func uniqueJSON(data []byte) bool         { return wire.UniqueJSON(data) }
