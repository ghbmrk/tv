package native

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
)

type editFixture struct {
	id             string
	calls          []string
	receipts       map[string]Receipt
	lost           bool
	override       json.RawMessage
	changeIdentity bool
}

func (f *editFixture) DeviceID() string { return f.id }
func (f *editFixture) Request(_ context.Context, op string, fields map[string]any, _ int64) (Response, error) {
	f.calls = append(f.calls, op)
	if op == "capabilities" {
		return Response{"ok", raw(map[string]bool{"receipt_operation_sha256": true})}, nil
	}
	if f.changeIdentity {
		f.id = strings.Repeat("b", 64)
	}
	id, _ := fields["request_id"].(string)
	if op == "receipt" {
		if f.override != nil {
			return Response{"ok", f.override}, nil
		}
		if r, ok := f.receipts[id]; ok {
			return Response{"ok", raw(r)}, nil
		}
		return Response{Status: "not_found"}, nil
	}
	fingerprint := fmt.Sprintf("apply:%d:%s", fields["base_revision"], digest(document))
	if op == "undo" {
		fingerprint = fmt.Sprintf("undo:%d:%d", fields["base_revision"], fields["restore_revision"])
	}
	r := Receipt{id, 8, 7, digest(document), digest(fingerprint)}
	f.receipts[id] = r
	if f.lost {
		return Response{}, errors.New(document)
	}
	return Response{"ok", raw(map[string]any{"receipt": r, "state": map[string]string{"document": document}})}, nil
}
func editSetup(t *testing.T) (*Editor, *editFixture, Edit) {
	t.Helper()
	f := &editFixture{id: device, receipts: map[string]Receipt{}}
	x, err := NewEditor(context.Background(), f)
	if err != nil {
		t.Fatal(err)
	}
	return x, f, Edit{RequestID: strings.Repeat("c", 64), Operation: "apply", BaseRevision: 7, Document: document}
}
func TestNativeEditorLostReplyReconcilesWithoutEffectReplay(t *testing.T) {
	x, f, e := editSetup(t)
	f.lost = true
	if got := x.Execute(context.Background(), e); got.Status != "unknown" || got.Receipt != nil {
		t.Fatal(got)
	}
	fresh, err := NewEditor(context.Background(), f)
	if err != nil {
		t.Fatal(err)
	}
	if got := fresh.Reconcile(context.Background(), e); got.Status != "committed" || got.Receipt == nil {
		t.Fatal(got)
	}
	if strings.Join(f.calls, ",") != "capabilities,apply,capabilities,receipt" {
		t.Fatal("unexpected retry", f.calls)
	}
}
func TestNativeEditorRejectsMalformedOrMismatchedReceipt(t *testing.T) {
	x, f, e := editSetup(t)
	if x.Execute(context.Background(), e).Status != "committed" {
		t.Fatal("fixture commit failed")
	}
	valid := f.receipts[e.RequestID]
	for _, mutate := range []func(*Receipt){func(r *Receipt) { r.PreviousRevision = 6 }, func(r *Receipt) { r.Revision = 9 }, func(r *Receipt) { r.RequestID = strings.Repeat("d", 64) }, func(r *Receipt) { r.OperationSHA256 = digest("different") }, func(r *Receipt) { r.DocumentSHA256 = digest("different") }} {
		r := valid
		mutate(&r)
		f.override = raw(r)
		if got := x.Reconcile(context.Background(), e); got.Status != "unknown" || got.Receipt != nil {
			t.Fatal("unverified receipt accepted", got)
		}
	}
	for _, value := range []string{`{}`, `{"request_id":"a","request_id":"b"}`, `{"Request_ID":"alias"}`, `null`} {
		f.override = json.RawMessage(value)
		if x.Reconcile(context.Background(), e).Status != "unknown" {
			t.Fatal("malformed receipt accepted")
		}
	}
	f.override = nil
	delete(f.receipts, e.RequestID)
	if x.Reconcile(context.Background(), e).Status != "unknown" {
		t.Fatal("absence proved non-application")
	}
}
func TestNativeEditorBoundsAndIdentityBeforeAndAfterDispatch(t *testing.T) {
	for _, mutate := range []func(*Edit){func(e *Edit) { e.Operation = "shell" }, func(e *Edit) { e.RequestID = "external" }, func(e *Edit) { e.BaseRevision = 0 }, func(e *Edit) { e.BaseRevision = maxExactInteger }, func(e *Edit) { e.Document = `{"x":1,"x":2}` }, func(e *Edit) { e.RestoreRevision = 1 }} {
		x, f, e := editSetup(t)
		mutate(&e)
		if got := x.Execute(context.Background(), e); got.Status != "refused" || len(f.calls) != 1 {
			t.Fatal("invalid edit dispatched", got)
		}
	}
	x, f, e := editSetup(t)
	f.id = strings.Repeat("b", 64)
	if x.Execute(context.Background(), e).Status != "refused" || len(f.calls) != 1 {
		t.Fatal("changed target received edit")
	}
	x, f, e = editSetup(t)
	f.changeIdentity = true
	if got := x.Execute(context.Background(), e); got.Status != "unknown" || got.Receipt != nil {
		t.Fatal("changed identity claimed commit", got)
	}
}
func TestNativeEditorUndoReceiptBindsRestoreRevision(t *testing.T) {
	x, _, e := editSetup(t)
	e.Operation = "undo"
	e.Document = ""
	e.RestoreRevision = 3
	if got := x.Execute(context.Background(), e); got.Status != "committed" {
		t.Fatal(got)
	}
	e.RestoreRevision = 4
	if got := x.Reconcile(context.Background(), e); got.Status != "unknown" || got.Receipt != nil {
		t.Fatal("wrong undo target accepted", got)
	}
}
