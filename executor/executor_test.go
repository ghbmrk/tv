package executor

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/ghbmrk/agentos/broker/journal"
)

const device = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
const document = `{"title":"PRIVATE-DOCUMENT-CANARY"}`

func digest(text string) string {
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}
func raw(value any) json.RawMessage { data, _ := json.Marshal(value); return data }

type fakeTransport struct {
	calls      []string
	fields     []map[string]any
	receipts   map[string]Receipt
	lost       bool
	refusal    string
	capability bool
	override   json.RawMessage
}

func (f *fakeTransport) DeviceID() string { return device }
func (f *fakeTransport) Request(_ context.Context, op string, fields map[string]any, _ int64) (Response, error) {
	f.calls = append(f.calls, op)
	f.fields = append(f.fields, fields)
	if op == "capabilities" {
		return Response{Status: "ok", Result: raw(map[string]any{"receipt_operation_sha256": f.capability})}, nil
	}
	id, _ := fields["request_id"].(string)
	if op == "receipt" {
		if f.override != nil {
			return Response{Status: "ok", Result: f.override}, nil
		}
		if r, ok := f.receipts[id]; ok {
			return Response{Status: "ok", Result: raw(r)}, nil
		}
		return Response{Status: "not_found"}, nil
	}
	if f.refusal != "" {
		return Response{Status: f.refusal}, nil
	}
	base := fields["base_revision"].(int64)
	docHash := digest(document)
	fingerprint := "apply:7:" + docHash
	if op == "undo" {
		fingerprint = "undo:7:3"
	}
	r := Receipt{RequestID: id, Revision: base + 1, PreviousRevision: base, DocumentSHA256: docHash, OperationSHA256: digest(fingerprint)}
	f.receipts[id] = r
	if f.lost {
		return Response{}, errors.New("PRIVATE-TRANSPORT-ERROR-CANARY")
	}
	return Response{Status: "ok", Result: raw(map[string]any{"receipt": r, "state": map[string]any{"document": document}})}, nil
}
func fixture(t *testing.T) (*Executor, *fakeTransport, journal.Intent) {
	t.Helper()
	f := &fakeTransport{capability: true, receipts: map[string]Receipt{}}
	x, err := New(context.Background(), Config{Namespace: "household-fixture", Account: "tv:living-room", Transport: f})
	if err != nil {
		t.Fatal(err)
	}
	in := journal.Intent{ID: "intent-fixture", Account: "tv:living-room", Executor: Name, Action: ActionApply,
		Params: map[string]any{"device_id": device, "base_revision": float64(7), "document": document}}
	return x, f, in
}
func TestActualJournalInterfaceAndLostReplyReconcileAfterAdapterRestart(t *testing.T) {
	x, f, in := fixture(t)
	var _ journal.Executor = x
	f.lost = true
	out := x.Execute(context.Background(), in, 1)
	if out.Result != journal.ResultUnknown || strings.Contains(out.Evidence, "CANARY") {
		t.Fatalf("unsafe outcome: %+v", out)
	}
	if strings.Join(f.calls, ",") != "capabilities,apply" {
		t.Fatalf("unexpected retry: %v", f.calls)
	}
	fresh, err := New(context.Background(), Config{Namespace: "household-fixture", Account: in.Account, Transport: f})
	if err != nil {
		t.Fatal(err)
	}
	out = fresh.Reconcile(context.Background(), in, 1)
	if out.Result != journal.ResultSucceeded || strings.Contains(out.Evidence, "CANARY") {
		t.Fatalf("receipt not reconciled safely: %+v", out)
	}
	if f.calls[len(f.calls)-1] != "receipt" {
		t.Fatal("reconcile dispatched an effect")
	}
}
func TestMissingOrMismatchedReceiptCannotProveOutcome(t *testing.T) {
	x, f, in := fixture(t)
	if out := x.Reconcile(context.Background(), in, 1); out.Result != journal.ResultUnknown {
		t.Fatal(out)
	}
	if out := x.Execute(context.Background(), in, 1); out.Result != journal.ResultSucceeded {
		t.Fatal(out)
	}
	changed := in
	changed.Params = map[string]any{"device_id": device, "base_revision": float64(7), "document": "{}"}
	if out := x.Reconcile(context.Background(), changed, 1); out.Result != journal.ResultUnknown {
		t.Fatal("wrong document accepted", out)
	}
	id := f.fields[1]["request_id"].(string)
	for _, mutate := range []func(*Receipt){func(r *Receipt) { r.OperationSHA256 = digest("undo:7:4") }, func(r *Receipt) { r.PreviousRevision = 6 }, func(r *Receipt) { r.Revision = 99 }, func(r *Receipt) { r.RequestID = "another-attempt" }} {
		original := f.receipts[id]
		modified := original
		mutate(&modified)
		f.receipts[id] = modified
		if out := x.Reconcile(context.Background(), in, 1); out.Result != journal.ResultUnknown {
			t.Fatal("mismatched receipt accepted", out)
		}
		f.receipts[id] = original
	}
}
func TestExactAttemptMappingAndAuthorityBoundary(t *testing.T) {
	x, f, in := fixture(t)
	x.Execute(context.Background(), in, 1)
	first := f.fields[len(f.fields)-1]["request_id"].(string)
	x.Execute(context.Background(), in, 1)
	if f.fields[len(f.fields)-1]["request_id"] != first || len(first) != 64 {
		t.Fatal("unstable request ID")
	}
	x.Execute(context.Background(), in, 2)
	if f.fields[len(f.fields)-1]["request_id"] == first {
		t.Fatal("attempts collided")
	}
	for _, change := range []func(*journal.Intent){func(i *journal.Intent) { i.Account = "tv:other" }, func(i *journal.Intent) { i.Executor = "shell" }, func(i *journal.Intent) { i.Action = "tv.purchase" }, func(i *journal.Intent) {
		i.Params = map[string]any{"device_id": strings.Repeat("b", 64), "base_revision": 7, "document": document}
	}, func(i *journal.Intent) {
		i.Params = map[string]any{"device_id": device, "base_revision": 7, "document": document, "shell": "refused"}
	}} {
		invalid := in
		change(&invalid)
		before := len(f.calls)
		if out := x.Execute(context.Background(), invalid, 1); out.Result != journal.ResultNotApplied || len(f.calls) != before {
			t.Fatal("invalid authority reached transport", out)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	before := len(f.calls)
	if out := x.Execute(ctx, in, 1); out.Result != journal.ResultNotApplied || len(f.calls) != before {
		t.Fatal(out)
	}
}
func TestUndoReceiptBindsExactRestoreTargetAndNumbersStayExact(t *testing.T) {
	x, f, in := fixture(t)
	in.Action = ActionUndo
	in.Params = map[string]any{"device_id": device, "base_revision": json.Number("7"), "restore_revision": json.Number("3")}
	if out := x.Execute(context.Background(), in, 1); out.Result != journal.ResultSucceeded {
		t.Fatal(out)
	}
	in.Params["restore_revision"] = json.Number("4")
	if out := x.Reconcile(context.Background(), in, 1); out.Result != journal.ResultUnknown {
		t.Fatal("different undo target matched", out)
	}
	for _, number := range []any{1.5, float64(9007199254740992), json.Number("9223372036854775807"), true, "7"} {
		in.Params["base_revision"] = number
		before := len(f.calls)
		if out := x.Execute(context.Background(), in, 1); out.Result != journal.ResultNotApplied || len(f.calls) != before {
			t.Fatal("invalid numeric value reached TV", number, out)
		}
	}
}
func TestOldEndpointIsRefusedBeforeAnEffectAndUnknownStatusStaysUnknown(t *testing.T) {
	f := &fakeTransport{receipts: map[string]Receipt{}}
	if _, err := New(context.Background(), Config{Namespace: "fixture", Account: "tv:a", Transport: f}); err == nil {
		t.Fatal("old endpoint admitted")
	}
	x, f, in := fixture(t)
	f.refusal = "unknown"
	if out := x.Execute(context.Background(), in, 1); out.Result != journal.ResultUnknown {
		t.Fatal(out)
	}
	f.refusal = "conflict"
	if out := x.Execute(context.Background(), in, 1); out.Result != journal.ResultNotApplied {
		t.Fatal(out)
	}
}

func TestReceiptAmbiguityAndServerTextNeverBecomeEvidence(t *testing.T) {
	x, f, in := fixture(t)
	if x.Execute(context.Background(), in, 1).Result != journal.ResultSucceeded {
		t.Fatal("fixture apply failed")
	}
	var receipt Receipt
	for _, r := range f.receipts {
		receipt = r
	}
	original := string(raw(receipt))
	for _, body := range []string{original[:len(original)-1] + `,"operation_sha256":"` + digest("other") + `"}`, original + ` trailing`, strings.Replace(original, `"revision":8`, `"revision":8.5`, 1)} {
		f.override = json.RawMessage(body)
		if out := x.Reconcile(context.Background(), in, 1); out.Result != journal.ResultUnknown || strings.Contains(out.Evidence, "PRIVATE") {
			t.Fatal("ambiguous receipt accepted", out)
		}
	}
	f.refusal = "PRIVATE-SERVER-CANARY"
	if out := x.Execute(context.Background(), in, 2); out.Result != journal.ResultUnknown || strings.Contains(out.Evidence, "CANARY") {
		t.Fatal(out)
	}
}

func TestOwnerNamespaceAndAccountSeparateIdempotencyKeys(t *testing.T) {
	x, f, in := fixture(t)
	x.Execute(context.Background(), in, 1)
	original := f.fields[len(f.fields)-1]["request_id"]
	for _, config := range []Config{{Namespace: "second-broker", Account: in.Account, Transport: f}, {Namespace: "household-fixture", Account: "tv:second", Transport: f}} {
		other, err := New(context.Background(), config)
		if err != nil {
			t.Fatal(err)
		}
		next := in
		next.Account = config.Account
		if other.Execute(context.Background(), next, 1).Result != journal.ResultSucceeded {
			t.Fatal("fixture dispatch failed")
		}
		if f.fields[len(f.fields)-1]["request_id"] == original {
			t.Fatal("owner namespaces collided")
		}
	}
}
