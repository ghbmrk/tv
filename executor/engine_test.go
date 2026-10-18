package executor

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"github.com/ghbmrk/agentos/broker/journal"
)

// This fixture policy is not production authority. It exercises the upstream
// engine's authorization/dispatch boundary with synthetic owner input only.
type fixturePolicy struct{ revoked bool }

func (p *fixturePolicy) Check(_ context.Context, _ journal.Phase, in journal.Intent) error {
	if p.revoked || in.Account != "tv:living-room" || in.Executor != Name || in.Action != ActionApply {
		return errors.New("synthetic policy denied")
	}
	return nil
}
func TestActualBrokerJournalRestartReconcilesWithoutAnotherTVEffect(t *testing.T) {
	x, f, in := fixture(t)
	in.Origin = "owner:fixture"
	f.lost = true
	path := filepath.Join(t.TempDir(), "journal")
	store, err := journal.OpenFile(path)
	if err != nil {
		t.Fatal(err)
	}
	policy := &fixturePolicy{}
	// All fixture inputs are synthetic; a production embedding must supply the
	// broker's actual redactor, grants and private-data routing.
	redact := func(s string) string { return s }
	engine, err := journal.Open(store, policy, map[string]journal.Executor{Name: x}, redact)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Submit(in); err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Authorize(context.Background(), in.ID); err != nil {
		t.Fatal(err)
	}
	status, err := engine.Dispatch(context.Background(), in.ID)
	if err != nil || status.State != journal.OutcomeUnknown {
		t.Fatal(status.State, err)
	}
	if _, err = engine.Dispatch(context.Background(), in.ID); !errors.Is(err, journal.ErrState) {
		t.Fatal("unknown effect retried", err)
	}
	if err = store.Close(); err != nil {
		t.Fatal(err)
	}
	store, err = journal.OpenFile(path)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	fresh, err := New(context.Background(), Config{Namespace: "household-fixture", Account: in.Account, Transport: f})
	if err != nil {
		t.Fatal(err)
	}
	engine, err = journal.Open(store, policy, map[string]journal.Executor{Name: fresh}, redact)
	if err != nil {
		t.Fatal(err)
	}
	if len(engine.Fenced(in.Account)) != 1 {
		t.Fatal("restart did not fence the uncertain account")
	}
	saved := f.receipts
	f.receipts = map[string]Receipt{}
	engine.Reconcile(context.Background())
	status, err = engine.Get(in.ID)
	if err != nil || status.State != journal.OutcomeUnknown || len(engine.Fenced(in.Account)) != 1 {
		t.Fatal("missing receipt settled the account", status.State, err)
	}
	f.receipts = saved
	engine.Reconcile(context.Background())
	status, err = engine.Get(in.ID)
	if err != nil || status.State != journal.Succeeded || len(engine.Fenced(in.Account)) != 0 {
		t.Fatal("receipt did not resolve restart", status.State, err)
	}
	count := 0
	for _, op := range f.calls {
		if op == "apply" {
			count++
		}
	}
	if count != 1 {
		t.Fatal("reconciliation replayed the TV effect", count)
	}
	changed := in
	changed.Params = map[string]any{"device_id": device, "base_revision": 7, "document": "{}"}
	if _, err = engine.Submit(changed); !errors.Is(err, journal.ErrConflict) {
		t.Fatal("changed intent parameters survived broker restart", err)
	}
}
func TestActualBrokerDispatchRechecksPolicyBeforeTVTransport(t *testing.T) {
	x, f, in := fixture(t)
	in.Origin = "owner:fixture"
	store, err := journal.OpenFile(filepath.Join(t.TempDir(), "journal"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	policy := &fixturePolicy{}
	engine, err := journal.Open(store, policy, map[string]journal.Executor{Name: x}, func(s string) string { return s })
	if err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Submit(in); err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Authorize(context.Background(), in.ID); err != nil {
		t.Fatal(err)
	}
	before := len(f.calls)
	policy.revoked = true
	if _, err = engine.Dispatch(context.Background(), in.ID); err == nil || len(f.calls) != before {
		t.Fatal("revoked dispatch reached TV transport", err)
	}
}

// The current upstream engine may retry key-honouring executors and park
// unresolved effects. A missing TV receipt must never authorize another edit.
func TestCurrentBrokerParksMissingReceiptWithoutResendingTVEffect(t *testing.T) {
	x, f, in := fixture(t)
	in.Origin = "owner:fixture"
	f.lost = true
	store, err := journal.OpenFile(filepath.Join(t.TempDir(), "journal"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	engine, err := journal.Open(store, &fixturePolicy{}, map[string]journal.Executor{Name: x}, func(s string) string { return s })
	if err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Submit(in); err != nil {
		t.Fatal(err)
	}
	if _, err = engine.Authorize(context.Background(), in.ID); err != nil {
		t.Fatal(err)
	}
	status, err := engine.Dispatch(context.Background(), in.ID)
	if err != nil || status.State != journal.OutcomeUnknown {
		t.Fatal(status.State, err)
	}
	saved := f.receipts
	f.receipts = map[string]Receipt{}
	for round := 0; round < 32 && len(engine.Parked()) == 0; round++ {
		engine.Reconcile(context.Background())
	}
	status, err = engine.Get(in.ID)
	if err != nil || status.State != journal.OutcomeUnknown || len(status.Attempts) != 1 || !status.Attempts[0].Parked || len(engine.Parked()) != 1 {
		t.Fatal("missing receipt did not remain a single parked unknown attempt", status, err)
	}
	for round := 0; round < 8; round++ {
		engine.Reconcile(context.Background())
	}
	countEffects := func() int {
		n := 0
		for _, op := range f.calls {
			if op == "apply" {
				n++
			}
		}
		return n
	}
	if countEffects() != 1 {
		t.Fatal("unknown/parked effect was sent again", countEffects())
	}
	f.receipts = saved
	engine.Reconcile(context.Background())
	status, err = engine.Get(in.ID)
	if err != nil || status.State != journal.Succeeded || len(status.Attempts) != 1 || len(engine.Parked()) != 0 || countEffects() != 1 {
		t.Fatal("original receipt did not settle the parked attempt without an edit", status, err)
	}
}
