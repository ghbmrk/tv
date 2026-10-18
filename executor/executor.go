// Package executor adapts the TV's native editing journal to agentOS's actual
// executor interface. It is an isolated broker component, never a guest tool.
package executor

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/ghbmrk/agentos/broker/journal"
)

const (
	Name                  = "sovereign-tv"
	ActionApply           = "tv.experience.apply"
	ActionUndo            = "tv.experience.undo"
	maxExactInteger int64 = 9007199254740991
)

var hexDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var localName = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

type Response struct {
	Status string
	Result json.RawMessage
}
type Transport interface {
	DeviceID() string
	Request(context.Context, string, map[string]any, int64) (Response, error)
}
type Config struct {
	Namespace, Account string
	Transport          Transport
}
type Executor struct {
	namespace, account, device string
	transport                  Transport
}

var _ journal.Executor = (*Executor)(nil)

// New verifies the receipt feature before enabling any effect. Namespace is an
// owner-assigned stable broker identity, retained across restarts/key rotation.
func New(ctx context.Context, cfg Config) (*Executor, error) {
	if cfg.Transport == nil || !localName.MatchString(cfg.Namespace) || !localName.MatchString(cfg.Account) || !hexDigest.MatchString(cfg.Transport.DeviceID()) {
		return nil, errors.New("invalid owner executor configuration")
	}
	response, err := cfg.Transport.Request(ctx, "capabilities", nil, expiry(ctx))
	var caps map[string]json.RawMessage
	var operationDigest bool
	if err != nil || response.Status != "ok" || !uniqueJSON(response.Result) || json.Unmarshal(response.Result, &caps) != nil || json.Unmarshal(caps["receipt_operation_sha256"], &operationDigest) != nil || !operationDigest {
		return nil, errors.New("TV receipt verification capability unavailable")
	}
	for key := range caps {
		if key != "receipt_operation_sha256" && strings.EqualFold(key, "receipt_operation_sha256") {
			return nil, errors.New("TV receipt verification capability unavailable")
		}
	}
	return &Executor{cfg.Namespace, cfg.Account, cfg.Transport.DeviceID(), cfg.Transport}, nil
}

type Receipt struct {
	RequestID        string `json:"request_id"`
	Revision         int64  `json:"revision"`
	PreviousRevision int64  `json:"previous_revision"`
	DocumentSHA256   string `json:"document_sha256"`
	OperationSHA256  string `json:"operation_sha256"`
}
type prepared struct {
	operation, id, fingerprint, documentHash string
	base                                     int64
	fields                                   map[string]any
}

func hash(text string) string { sum := sha256.Sum256([]byte(text)); return hex.EncodeToString(sum[:]) }
func number(value any) (int64, bool) {
	var n int64
	switch v := value.(type) {
	case int:
		n = int64(v)
	case int64:
		n = v
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) || v != math.Trunc(v) || v < 1 || v > float64(maxExactInteger) {
			return 0, false
		}
		n = int64(v)
	case json.Number:
		var err error
		n, err = strconv.ParseInt(string(v), 10, 64)
		if err != nil {
			return 0, false
		}
	default:
		return 0, false
	}
	return n, n > 0 && n <= maxExactInteger
}
func (x *Executor) prepare(in journal.Intent, attempt int) (prepared, bool) {
	if in.Account != x.account || in.Executor != Name || in.ID == "" || len(in.ID) > 256 || !utf8.ValidString(in.ID) || attempt < 1 {
		return prepared{}, false
	}
	if in.Params["device_id"] != x.device {
		return prepared{}, false
	}
	base, ok := number(in.Params["base_revision"])
	if !ok || base == maxExactInteger {
		return prepared{}, false
	}
	key, _ := json.Marshal([]string{"sovereign-tv/native-v1", x.namespace, x.account, x.device, journal.AttemptKey(in.ID, attempt)})
	p := prepared{id: hash(string(key)), base: base, fields: map[string]any{"base_revision": base}}
	p.fields["request_id"] = p.id
	switch in.Action {
	case ActionApply:
		doc, ok := in.Params["document"].(string)
		if !ok || len(in.Params) != 3 || len(doc) > 65536 || !utf8.ValidString(doc) || !json.Valid([]byte(doc)) || !bytes.HasPrefix(bytes.TrimSpace([]byte(doc)), []byte("{")) {
			return prepared{}, false
		}
		p.operation = "apply"
		p.documentHash = hash(doc)
		p.fields["document"] = doc
		p.fingerprint = hash(fmt.Sprintf("apply:%d:%s", base, p.documentHash))
	case ActionUndo:
		restore, ok := number(in.Params["restore_revision"])
		if !ok || len(in.Params) != 3 || restore >= base {
			return prepared{}, false
		}
		p.operation = "undo"
		p.fields["restore_revision"] = restore
		p.fingerprint = hash(fmt.Sprintf("undo:%d:%d", base, restore))
	default:
		return prepared{}, false
	}
	return p, true
}
func expiry(ctx context.Context) int64 {
	until := time.Now().Add(10 * time.Second)
	if deadline, ok := ctx.Deadline(); ok && deadline.Before(until) {
		until = deadline
	}
	return until.UnixMilli()
}
func unknown(reason string) journal.Outcome {
	return journal.Outcome{Result: journal.ResultUnknown, Evidence: reason}
}
func refused(reason string) journal.Outcome {
	return journal.Outcome{Result: journal.ResultNotApplied, Evidence: reason}
}
func decodeExact(data []byte, value any) bool {
	if !uniqueJSON(data) {
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
func uniqueJSON(data []byte) bool {
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
func (x *Executor) verified(p prepared, raw json.RawMessage) journal.Outcome {
	var receipt Receipt
	if !decodeExact(raw, &receipt) || receipt.RequestID != p.id || receipt.PreviousRevision != p.base || receipt.Revision != p.base+1 || !hexDigest.MatchString(receipt.DocumentSHA256) || receipt.OperationSHA256 != p.fingerprint || (p.documentHash != "" && receipt.DocumentSHA256 != p.documentHash) {
		return unknown("TV receipt does not verify this attempt")
	}
	// Deliberately exclude documents, titles, server text, paths and certificates.
	evidence, _ := json.Marshal(struct {
		Kind   string `json:"kind"`
		Device string `json:"device_id"`
		Receipt
	}{"native_commit_receipt", x.device, receipt})
	return journal.Outcome{Result: journal.ResultSucceeded, Evidence: string(evidence)}
}
func (x *Executor) Execute(ctx context.Context, in journal.Intent, attempt int) journal.Outcome {
	p, ok := x.prepare(in, attempt)
	if !ok || ctx.Err() != nil {
		return refused("TV effect not dispatched: invalid target, operation, arguments or context")
	}
	response, err := x.transport.Request(ctx, p.operation, p.fields, expiry(ctx))
	if err != nil {
		return unknown("TV effect unconfirmed; reconcile the original attempt")
	}
	if response.Status == "ok" {
		var body struct {
			Receipt json.RawMessage `json:"receipt"`
			State   json.RawMessage `json:"state"`
		}
		if !decodeExact(response.Result, &body) {
			return unknown("TV effect reply did not contain a verifiable receipt")
		}
		return x.verified(p, body.Receipt)
	}
	// The broker contract dispatches Execute at most once per intent/attempt.
	// These are the native service's definite pre-commit refusals for that dispatch.
	switch response.Status {
	case "invalid", "expired", "unauthorized", "conflict", "capacity":
		return refused("TV refused this dispatch: " + response.Status)
	}
	return unknown("TV effect outcome unavailable")
}
func (x *Executor) Reconcile(ctx context.Context, in journal.Intent, attempt int) journal.Outcome {
	p, ok := x.prepare(in, attempt)
	if !ok || ctx.Err() != nil {
		return unknown("TV attempt cannot be reconciled with these parameters")
	}
	response, err := x.transport.Request(ctx, "receipt", map[string]any{"request_id": p.id}, expiry(ctx))
	if err != nil || response.Status != "ok" {
		return unknown("No verifying TV receipt available; no effect replayed")
	}
	return x.verified(p, response.Result)
}
