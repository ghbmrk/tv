// Package executor retains the legacy agentOS journal adapter. Current broker
// integration lives in kernelclerk; both use the same native edit protocol.
package executor

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math"
	"regexp"
	"strconv"
	"unicode/utf8"

	"github.com/ghbmrk/agentos/broker/journal"
	"github.com/ghbmrk/tv/executor/native"
)

const (
	Name                  = "sovereign-tv"
	ActionApply           = "tv.experience.apply"
	ActionUndo            = "tv.experience.undo"
	maxExactInteger int64 = 9007199254740991
)

var hexDigest = regexp.MustCompile(`^[a-f0-9]{64}$`)
var localName = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

type Response = native.Response
type Transport = native.Transport
type Receipt = native.Receipt
type Config struct {
	Namespace, Account string
	Transport          Transport
}
type Executor struct {
	namespace, account, device string
	editor                     *native.Editor
}

var _ journal.Executor = (*Executor)(nil)

func New(ctx context.Context, cfg Config) (*Executor, error) {
	if cfg.Transport == nil || !localName.MatchString(cfg.Namespace) || !localName.MatchString(cfg.Account) || !hexDigest.MatchString(cfg.Transport.DeviceID()) {
		return nil, errors.New("invalid owner executor configuration")
	}
	editor, err := native.NewEditor(ctx, cfg.Transport)
	if err != nil {
		return nil, err
	}
	return &Executor{cfg.Namespace, cfg.Account, editor.DeviceID(), editor}, nil
}
func hash(s string) string { b := sha256.Sum256([]byte(s)); return hex.EncodeToString(b[:]) }
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

func (x *Executor) prepare(in journal.Intent, attempt int) (native.Edit, bool) {
	if in.Account != x.account || in.Executor != Name || in.ID == "" || len(in.ID) > 256 || !utf8.ValidString(in.ID) || attempt < 1 || len(in.Params) != 3 || in.Params["device_id"] != x.device {
		return native.Edit{}, false
	}
	base, ok := number(in.Params["base_revision"])
	if !ok {
		return native.Edit{}, false
	}
	key, _ := json.Marshal([]string{"sovereign-tv/native-v1", x.namespace, x.account, x.device, journal.AttemptKey(in.ID, attempt)})
	edit := native.Edit{RequestID: hash(string(key)), BaseRevision: base}
	switch in.Action {
	case ActionApply:
		edit.Operation = "apply"
		edit.Document, ok = in.Params["document"].(string)
	case ActionUndo:
		edit.Operation = "undo"
		edit.RestoreRevision, ok = number(in.Params["restore_revision"])
	default:
		return native.Edit{}, false
	}
	return edit, ok && native.ValidateEdit(edit)
}
func unknown(reason string) journal.Outcome {
	return journal.Outcome{Result: journal.ResultUnknown, Evidence: reason}
}
func refused(reason string) journal.Outcome {
	return journal.Outcome{Result: journal.ResultNotApplied, Evidence: reason}
}
func (x *Executor) outcome(out native.Outcome) journal.Outcome {
	switch out.Status {
	case "committed":
		if out.Receipt == nil {
			return unknown("TV receipt unavailable")
		}
		evidence, _ := json.Marshal(struct {
			Kind     string `json:"kind"`
			DeviceID string `json:"device_id"`
			Receipt
		}{"native_commit_receipt", x.device, *out.Receipt})
		return journal.Outcome{Result: journal.ResultSucceeded, Evidence: string(evidence)}
	case "refused":
		return refused("TV refused this dispatch")
	default:
		return unknown("TV effect unconfirmed; reconcile the original attempt")
	}
}
func (x *Executor) Execute(ctx context.Context, in journal.Intent, attempt int) journal.Outcome {
	edit, ok := x.prepare(in, attempt)
	if !ok || ctx.Err() != nil {
		return refused("TV effect not dispatched: invalid target, operation, arguments or context")
	}
	return x.outcome(x.editor.Execute(ctx, edit))
}
func (x *Executor) Reconcile(ctx context.Context, in journal.Intent, attempt int) journal.Outcome {
	edit, ok := x.prepare(in, attempt)
	if !ok || ctx.Err() != nil {
		return unknown("TV attempt cannot be reconciled with these parameters")
	}
	return x.outcome(x.editor.Reconcile(ctx, edit))
}
