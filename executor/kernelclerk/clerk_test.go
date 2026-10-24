//go:build linux

package kernelclerk

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/ghbmrk/agentos/broker/kernel"
	"github.com/ghbmrk/agentos/broker/kernel/key"
	"github.com/ghbmrk/agentos/broker/kernel/proc"
	"github.com/ghbmrk/tv/executor/native"
)

const testDevice = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
const privateDocument = `{"title":"PRIVATE-CONFIGURATION-CANARY"}`

func hashText(s string) string     { b := sha256.Sum256([]byte(s)); return hex.EncodeToString(b[:]) }
func encode(v any) json.RawMessage { b, _ := json.Marshal(v); return b }

type testTV struct {
	mu           sync.Mutex
	receipts     map[string]native.Receipt
	edits        int
	lost, hide   bool
	lastDocument string
}

func (v *testTV) DeviceID() string { return testDevice }
func (v *testTV) Request(_ context.Context, op string, fields map[string]any, _ int64) (native.Response, error) {
	v.mu.Lock()
	defer v.mu.Unlock()
	if op == "capabilities" {
		return native.Response{Status: "ok", Result: encode(map[string]bool{"receipt_operation_sha256": true})}, nil
	}
	id, _ := fields["request_id"].(string)
	if op == "receipt" {
		if r, ok := v.receipts[id]; ok && !v.hide {
			return native.Response{Status: "ok", Result: encode(r)}, nil
		}
		return native.Response{Status: "not_found"}, nil
	}
	if op != "apply" && op != "undo" {
		return native.Response{}, errors.New("unexpected synthetic operation")
	}
	base := fields["base_revision"].(int64)
	document, _ := fields["document"].(string)
	fingerprint := fmt.Sprintf("apply:%d:%s", base, hashText(document))
	if op == "undo" {
		fingerprint = fmt.Sprintf("undo:%d:%d", base, fields["restore_revision"].(int64))
		document = privateDocument
	}
	r, exists := v.receipts[id]
	if exists && r.OperationSHA256 != hashText(fingerprint) {
		return native.Response{Status: "conflict"}, nil
	}
	if !exists {
		r = native.Receipt{RequestID: id, Revision: base + 1, PreviousRevision: base, DocumentSHA256: hashText(document), OperationSHA256: hashText(fingerprint)}
		v.receipts[id] = r
		v.edits++
		v.lastDocument = document
	}
	if v.lost {
		return native.Response{}, errors.New(privateDocument)
	}
	return native.Response{Status: "ok", Result: encode(map[string]any{"receipt": r, "state": map[string]string{"document": document}})}, nil
}

type harness struct {
	t                             *testing.T
	owner, backup, holder, signer ed25519.PrivateKey
	store                         kernel.Store
	anchor                        *kernel.MemAnchor
	engine                        *kernel.Kernel
	clerk                         *Clerk
	transport                     *testTV
	root, grant                   key.Key
	now                           int64
	audience                      string
}

func privateKey(t *testing.T) ed25519.PrivateKey {
	t.Helper()
	_, p, e := ed25519.GenerateKey(rand.Reader)
	if e != nil {
		t.Fatal(e)
	}
	return p
}
func public(p ed25519.PrivateKey) ed25519.PublicKey { return p.Public().(ed25519.PublicKey) }
func check(t *testing.T, e error) {
	t.Helper()
	if e != nil {
		t.Fatal(e)
	}
}
func fixture(t *testing.T, audience string) *harness {
	return fixtureStore(t, audience, &kernel.MemStore{})
}
func fixtureStore(t *testing.T, audience string, store kernel.Store) *harness {
	h := &harness{t: t, owner: privateKey(t), backup: privateKey(t), holder: privateKey(t), signer: privateKey(t), store: store, anchor: &kernel.MemAnchor{}, now: 1700000000000, audience: audience, transport: &testTV{receipts: map[string]native.Receipt{}}}
	h.reboot()
	h.root = key.Issue(h.owner, key.Root{Clerk: "tv-fixture", Verbs: []key.Verb{key.ChangeAccount}, Serial: "synthetic-tv-root"})
	var err error
	h.grant, err = key.ClerkKey(h.root, h.owner, public(h.holder), h.now, 100000, key.LimitContent("private"), key.LimitLabels(Label), key.LimitHold(1000, 1000))
	check(t, err)
	digest := kernel.BatchHash(h.root, h.grant)
	check(t, h.engine.Issue(h.now-kernel.GrantHold, []key.Cosign{key.Approve(h.owner, digest), key.Approve(h.backup, digest)}, h.root, h.grant))
	return h
}
func (h *harness) reboot() {
	var err error
	h.clerk, err = New(context.Background(), Config{Name: "tv-fixture", Namespace: "kernel-fixture", Audience: h.audience, Visibility: "local-only", Anchors: []ed25519.PublicKey{public(h.owner), public(h.backup)}, Transport: h.transport, Clock: func() int64 { return h.now }})
	check(h.t, err)
	l, err := kernel.Open(kernel.Config{Store: h.store, Anchor: h.anchor, Pub: public(h.signer), Sign: h.signer, Rand: rand.Reader})
	check(h.t, err)
	h.engine, err = kernel.Boot(l, []ed25519.PublicKey{public(h.owner), public(h.backup)}, map[string]kernel.Clerk{"tv-fixture": h.clerk}, h.now)
	check(h.t, err)
}
func (h *harness) plan(id string, owner bool) kernel.Plan {
	ky, sign := h.grant, h.holder
	if owner {
		ky, sign = h.root, h.owner
	}
	step := kernel.PlanStep{Verb: key.ChangeAccount, Clerk: "tv-fixture", Content: "private", Labels: []string{Label}, Args: map[string]string{"target": h.clerk.Target(), "value": string(encode(Command{Operation: "apply", BaseRevision: 7, Document: privateDocument}))}}
	return kernel.SignPlan(kernel.Plan{ID: id, Key: ky, Steps: []kernel.PlanStep{step}}, sign)
}
func (h *harness) dispatch(p kernel.Plan) kernel.Call {
	check(h.t, h.engine.Submit(h.now, p))
	_, err := h.engine.Calls(h.now)
	check(h.t, err)
	h.now += 1001
	calls, err := h.engine.Calls(h.now)
	check(h.t, err)
	// Bare-owner plans may dispatch immediately, so tests use a separate
	// path for those rather than discarding an immediate call.
	if len(calls) != 1 {
		h.t.Fatalf("expected one dispatch; status=%+v calls=%+v", h.engine.State().Plans[p.ID], calls)
	}
	return calls[0]
}

func TestActualKernelLostReplyRestartAndRevocationOnlyProbe(t *testing.T) {
	h := fixture(t, "owner")
	h.transport.lost = true
	call := h.dispatch(h.plan("lost-reply", false))
	out := h.clerk.Do(call.Req, h.engine.State())
	if out.Outcome != "unknown" || strings.Contains(out.Detail, "CANARY") {
		t.Fatal(out)
	}
	// Process loss before Answer: the same real encrypted/hash-chained log
	// is reopened, not a fake view or a copied executor interface.
	h.reboot()
	h.transport.hide = true
	check(t, h.engine.Revoke(h.now, h.grant.Tip()))
	for n := 0; n < 8; n++ {
		h.now += 100000
		check(t, h.engine.Tick(h.now))
	}
	if h.transport.edits != 1 {
		t.Fatal("uncertain effect replayed", h.transport.edits)
	}
	if got := h.clerk.Probe(call.Req, h.engine.State()); got.Outcome != "unknown" {
		t.Fatal("absence claimed completion", got)
	}
	h.transport.hide = false
	if got := h.clerk.Probe(call.Req, h.engine.State()); got.Outcome != "done" || strings.Contains(got.Detail, "CANARY") {
		t.Fatal("revocation prevented receipt settlement", got)
	}
	if h.transport.edits != 1 {
		t.Fatal("probe sent another edit")
	}
}

func TestRealKernelRechecksAuthorityAndFactsBeforeEffect(t *testing.T) {
	for _, kind := range []string{"revoked", "expired", "stopped", "forged-signature", "changed-value", "missing-dispatch", "wrong-content", "wrong-label"} {
		t.Run(kind, func(t *testing.T) {
			h := fixture(t, "owner")
			p := h.plan("authority", false)
			if kind == "wrong-content" {
				p.Steps[0].Content = "public"
				p = kernel.SignPlan(p, h.holder)
			}
			if kind == "wrong-label" {
				p.Steps[0].Labels = nil
				p = kernel.SignPlan(p, h.holder)
			}
			if kind == "wrong-content" || kind == "wrong-label" {
				r := kernel.Request{Plan: p}
				if got := h.clerk.Do(r, h.engine.State()); got.Outcome != "failed" || h.transport.edits != 0 {
					t.Fatal("incorrect content facts admitted", got)
				}
				return
			}
			call := h.dispatch(p)
			r := call.Req
			switch kind {
			case "revoked":
				check(t, h.engine.Revoke(h.now, h.grant.Tip()))
			case "expired":
				h.now += key.ClerkLife + 1
			case "stopped":
				check(t, h.engine.Stop(h.now))
			case "forged-signature":
				r.Plan.Sig = make([]byte, ed25519.SignatureSize)
			case "changed-value":
				r.Plan.Steps = append([]kernel.PlanStep(nil), r.Plan.Steps...)
				r.Plan.Steps[0].Args = map[string]string{"target": h.clerk.Target(), "value": string(encode(Command{Operation: "apply", BaseRevision: 7, Document: `{}`}))}
			case "missing-dispatch":
				r.Plan.ID = "not-logged"
				r.Plan = kernel.SignPlan(r.Plan, h.holder)
			}
			if got := h.clerk.Do(r, h.engine.State()); got.Outcome != "failed" || h.transport.edits != 0 {
				t.Fatal("authority bypass", kind, got, h.transport.edits)
			}
		})
	}
}

func TestHouseholdRejectsDelegationButAcceptsOwnerSignedExactPlan(t *testing.T) {
	h := fixture(t, "household")
	call := h.dispatch(h.plan("delegated", false))
	result := h.clerk.Do(call.Req, h.engine.State())
	if result.Outcome != "failed" || h.transport.edits != 0 {
		t.Fatal("delegation became disclosure authority", result)
	}
	check(t, h.engine.Answer(h.now, call, result))
	p := h.plan("owner-plan", true)
	p.Cosigns = []key.Cosign{key.Approve(h.owner, kernel.PlanHash(p)), key.Approve(h.backup, kernel.PlanHash(p))}
	check(t, h.engine.Submit(h.now, p))
	calls, err := h.engine.Calls(h.now)
	check(t, err)
	if len(calls) != 1 {
		t.Fatalf("owner exact plan not dispatched: %+v", h.engine.State().Plans[p.ID])
	}
	if got := h.clerk.Do(calls[0].Req, h.engine.State()); got.Outcome != "ok" || h.transport.edits != 1 {
		t.Fatal("owner exact plan refused", got)
	}
}

func TestProbeCannotBorrowAnotherPlanSignatureOrChangeArguments(t *testing.T) {
	h := fixture(t, "owner")
	call := h.dispatch(h.plan("committed", false))
	if got := h.clerk.Do(call.Req, h.engine.State()); got.Outcome != "ok" {
		t.Fatal(got)
	}
	for _, kind := range []string{"document", "signature", "target", "verb", "extra-field", "case-alias", "request-id"} {
		t.Run(kind, func(t *testing.T) {
			var r kernel.Request
			check(t, json.Unmarshal(encode(call.Req), &r))
			switch kind {
			case "document":
				r.Plan.Steps[0].Args["value"] = string(encode(Command{Operation: "apply", BaseRevision: 7, Document: `{}`}))
				r.Plan = kernel.SignPlan(r.Plan, h.holder)
			case "signature":
				r.Plan.Sig = make([]byte, 64)
			case "target":
				r.Plan.Steps[0].Args["target"] = "tv:" + strings.Repeat("b", 64)
			case "verb":
				r.Plan.Steps[0].Verb = key.Present
			case "extra-field":
				r.Plan.Steps[0].Args["extra"] = "not-declared"
			case "case-alias":
				r.Plan.Steps[0].Args["value"] = `{"Operation":"apply","base_revision":7,"document":"{}"}`
			case "request-id":
				r.Plan.Steps[0].Args["value"] = `{"operation":"apply","base_revision":7,"document":"{}","request_id":"foreign"}`
			}
			if got := h.clerk.Probe(r, h.engine.State()); got.Outcome != "unknown" || h.transport.edits != 1 {
				t.Fatal("foreign receipt accepted", kind, got)
			}
		})
	}
}

func TestDeclarationAndSignedSnapshotBoundaries(t *testing.T) {
	h := fixture(t, "owner")
	for _, cfg := range []Config{{}, {Name: "tv-fixture", Namespace: "fixture", Audience: "public", Visibility: "local-only"}, {Name: "tv-fixture", Namespace: "fixture", Audience: "owner", Visibility: "unknown"}} {
		if _, err := New(context.Background(), cfg); err == nil {
			t.Fatal("unknown declaration accepted")
		}
	}
	call := h.dispatch(h.plan("snapshot", false))
	var external kernel.Request
	check(t, json.Unmarshal(encode(call.Req), &external))
	h.clerk.clock = func() int64 { external.Plan.Steps[0].Args["value"] = "mutated after snapshot"; return h.now }
	if got := h.clerk.Do(external, h.engine.State()); got.Outcome != "ok" || h.transport.lastDocument != privateDocument {
		t.Fatal("mutable caller changed checked edit", got)
	}
	if got := h.clerk.Do(call.Req, h.engine.State()); got.Outcome != "ok" || h.transport.edits != 1 {
		t.Fatal("duplicate step committed twice", got)
	}
}

// This uses the upstream fsynced/locked file store, with a synthetic retained
// anchor. It does not qualify production rollback protection or power loss.
func TestFileBackedKernelSettlesLostReplyAfterStoreReopen(t *testing.T) {
	path := filepath.Join(t.TempDir(), "kernel.log")
	store, err := proc.OpenFileStore(path)
	check(t, err)
	h := fixtureStore(t, "owner", store)
	h.transport.lost = true
	call := h.dispatch(h.plan("file-backed-lost-reply", false))
	if got := h.clerk.Do(call.Req, h.engine.State()); got.Outcome != "unknown" {
		t.Fatal(got)
	}
	check(t, store.Close())
	data, err := os.ReadFile(path)
	check(t, err)
	if len(data) == 0 || bytes.Contains(data, []byte("PRIVATE-CONFIGURATION-CANARY")) {
		t.Fatal("kernel log absent or private command stored in plaintext")
	}
	reopened, err := proc.OpenFileStore(path)
	check(t, err)
	defer reopened.Close()
	h.store = reopened
	h.reboot()
	check(t, h.engine.Revoke(h.now, h.grant.Tip()))
	if got := h.clerk.Probe(call.Req, h.engine.State()); got.Outcome != "done" || h.transport.edits != 1 {
		t.Fatal("file-backed restart failed to settle the existing effect", got)
	}
}

// Exercise the exported kernel-to-clerk socket protocol as well as direct
// calls. Same-UID fixtures do not establish production UID/network isolation.
func TestKernelClerkWireRoundTripAndPeerCheck(t *testing.T) {
	h := fixture(t, "owner")
	path := filepath.Join(t.TempDir(), "clerk.sock")
	ln, err := proc.ListenClerk(path, os.Getuid())
	check(t, err)
	done := make(chan error, 1)
	go func() { done <- proc.ServeClerk(ln, h.clerk, h.clerk.anchors) }()
	defer func() { ln.Close(); <-done }()
	remote := proc.Remote{Socket: path, UID: os.Getuid()}.Clerk(h.clerk.anchors)
	call := h.dispatch(h.plan("wire-lost-reply", false))
	h.transport.lost = true
	got := remote.Do(call.Req, h.engine.State())
	if got.Outcome != "unknown" || strings.Contains(got.Detail, "CANARY") || h.transport.edits != 1 {
		t.Fatal("wire dispatch violated uncertainty or disclosure boundary", got)
	}
	check(t, h.engine.Revoke(h.now, h.grant.Tip()))
	if got := remote.Probe(call.Req, h.engine.State()); got.Outcome != "done" || h.transport.edits != 1 {
		t.Fatal("wire reconciliation lost original receipt", got)
	}
	wrongPeer := proc.Remote{Socket: path, UID: os.Getuid() + 1}.Clerk(h.clerk.anchors)
	if got := wrongPeer.Do(call.Req, h.engine.State()); got.Outcome != kernel.OUnsent || h.transport.edits != 1 {
		t.Fatal("wrong clerk peer received request", got)
	}
}
