//go:build linux

// Owned-emulator integration probe, not a broker registration or guest tool.
package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/ghbmrk/agentos/broker/kernel"
	"github.com/ghbmrk/agentos/broker/kernel/key"
	"github.com/ghbmrk/tv/executor/kernelclerk"
	tv "github.com/ghbmrk/tv/executor/native"
)

func run() error {
	port := flag.Int("port", 0, "Owned-emulator localhost forward")
	device := flag.String("device-certificate", "", "Synthetic public device certificate")
	certificate := flag.String("client-certificate", "", "Synthetic public executor certificate")
	clientKey := flag.String("client-key", "", "Private temporary executor key")
	flag.Parse()
	if os.Getenv("SOVEREIGN_OWNED_EMULATOR") != "1" || flag.NArg() != 0 {
		return errors.New("owned emulator required")
	}
	client, err := tv.NewClient(tv.Profile{Address: "127.0.0.1", Port: *port, DeviceCertificate: *device, ClientCertificate: *certificate, ClientKey: *clientKey}, true)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	inspect, err := tv.NewInspector(client)
	if err != nil {
		return err
	}
	if _, err = inspect.Applications(ctx); err != nil {
		return err
	}
	state := func() (int64, string, error) {
		value, err := inspect.State(ctx)
		return value.Revision, value.Document, err
	}
	base, original, err := state()
	if err != nil {
		return err
	}
	var doc map[string]json.RawMessage
	if err = json.Unmarshal([]byte(original), &doc); err != nil {
		return err
	}
	doc["title"] = json.RawMessage(`"Go household executor qualification"`)
	encoded, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	preview, err := inspect.Preview(ctx, base, string(encoded))
	if err != nil || preview.Revision != base || preview.Document != string(encoded) {
		return errors.New("preview mismatch")
	}
	unchanged, stillOriginal, err := state()
	if err != nil || unchanged != base || stillOriginal != original {
		return errors.New("validation preview changed saved state")
	}

	// These keys, grants, clock and in-memory kernel log are synthetic fixtures,
	// not production owner authority. The paired native endpoint is real.
	freshKey := func() (ed25519.PrivateKey, error) { _, p, e := ed25519.GenerateKey(rand.Reader); return p, e }
	owner, err := freshKey()
	if err != nil {
		return err
	}
	backup, err := freshKey()
	if err != nil {
		return err
	}
	holder, err := freshKey()
	if err != nil {
		return err
	}
	signer, err := freshKey()
	if err != nil {
		return err
	}
	pub := func(p ed25519.PrivateKey) ed25519.PublicKey { return p.Public().(ed25519.PublicKey) }
	anchors := []ed25519.PublicKey{pub(owner), pub(backup)}
	now := time.Now().UnixMilli()
	cfg := kernelclerk.Config{Name: "tv:emulator", Namespace: "owned-emulator-kernel", Audience: "owner", Visibility: "local-only", Anchors: anchors, Transport: client, Clock: func() int64 { return now }}
	x, err := kernelclerk.New(ctx, cfg)
	if err != nil {
		return err
	}
	store, anchor := &kernel.MemStore{}, &kernel.MemAnchor{}
	logConfig := kernel.Config{Store: store, Anchor: anchor, Pub: pub(signer), Sign: signer, Rand: rand.Reader}
	log, err := kernel.Open(logConfig)
	if err != nil {
		return err
	}
	engine, err := kernel.Boot(log, anchors, map[string]kernel.Clerk{cfg.Name: x}, now)
	if err != nil {
		return err
	}
	root := key.Issue(owner, key.Root{Clerk: cfg.Name, Verbs: []key.Verb{key.ChangeAccount}, Serial: "owned-emulator-only"})
	grant, err := key.ClerkKey(root, owner, pub(holder), now, 1000, key.LimitContent("private"), key.LimitLabels(kernelclerk.Label), key.LimitHold(1, 1))
	if err != nil {
		return err
	}
	batch := kernel.BatchHash(root, grant)
	if err = engine.Issue(now-kernel.GrantHold, []key.Cosign{key.Approve(owner, batch), key.Approve(backup, batch)}, root, grant); err != nil {
		return err
	}
	random := make([]byte, 16)
	if _, err = rand.Read(random); err != nil {
		return err
	}
	planID := hex.EncodeToString(random)
	dispatch := func(id string, command kernelclerk.Command) (kernel.Call, error) {
		value, e := json.Marshal(command)
		if e != nil {
			return kernel.Call{}, e
		}
		plan := kernel.SignPlan(kernel.Plan{ID: id, Key: grant, Steps: []kernel.PlanStep{{Verb: key.ChangeAccount, Clerk: cfg.Name, Content: "private", Labels: []string{kernelclerk.Label}, Args: map[string]string{"target": x.Target(), "value": string(value)}}}}, holder)
		if e = engine.Submit(now, plan); e != nil {
			return kernel.Call{}, e
		}
		if _, e = engine.Calls(now); e != nil {
			return kernel.Call{}, e
		}
		now += 2
		calls, e := engine.Calls(now)
		if e != nil || len(calls) != 1 || calls[0].Kind != kernel.ActDispatch {
			return kernel.Call{}, errors.New("synthetic kernel dispatch refused")
		}
		return calls[0], nil
	}
	call, err := dispatch(planID, kernelclerk.Command{Operation: "apply", BaseRevision: base, Document: string(encoded)})
	if err != nil {
		return err
	}
	applied := x.Do(call.Req, engine.State())
	if applied.Outcome != "ok" {
		return errors.New("current clerk apply unconfirmed")
	}
	if x.Do(call.Req, engine.State()) != applied {
		return errors.New("current clerk exact retry changed outcome")
	}
	if err = engine.Answer(now, call, applied); err != nil {
		return err
	}
	fresh, err := kernelclerk.New(ctx, cfg)
	if err != nil {
		return err
	}
	log, err = kernel.Open(logConfig)
	if err != nil {
		return err
	}
	engine, err = kernel.Boot(log, anchors, map[string]kernel.Clerk{cfg.Name: fresh}, now)
	if err != nil {
		return err
	}
	if fresh.Probe(call.Req, engine.State()).Outcome != "done" {
		return errors.New("current clerk reconciliation failed")
	}
	revision, current, err := state()
	if err != nil || revision != base+1 || current != string(encoded) {
		return errors.New("readback mismatch")
	}
	if _, err = inspect.Preview(ctx, base, string(encoded)); !errors.Is(err, tv.ErrStaleRevision) {
		return errors.New("stale preview not refused")
	}

	undo, err := dispatch(planID+"-undo", kernelclerk.Command{Operation: "undo", BaseRevision: base + 1, RestoreRevision: base})
	if err != nil {
		return err
	}
	undone := fresh.Do(undo.Req, engine.State())
	if undone.Outcome != "ok" {
		return errors.New("current clerk undo unconfirmed")
	}
	if err = engine.Answer(now, undo, undone); err != nil {
		return err
	}
	revision, current, err = state()
	if err != nil || revision != base+2 || current != original {
		return errors.New("undo readback mismatch")
	}
	fmt.Println(`{"go_executor":true,"state_inspection":true,"validation_preview":true,"application_discovery":true,"stale_preview_refused":true,"operation_receipt_verified":true,"reconcile":true,"exact_retry":true,"undo":true,"agentos_qualified":false,"kernel_clerk":true}`)
	return nil
}
func main() {
	if run() != nil {
		fmt.Fprintln(os.Stderr, "Owned-emulator Go executor qualification failed; no raw evidence printed.")
		os.Exit(1)
	}
}
