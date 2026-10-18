// Owned-emulator integration probe, not a broker registration or guest tool.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/ghbmrk/agentos/broker/journal"
	tv "github.com/ghbmrk/tv/executor"
)

func run() error {
	port := flag.Int("port", 0, "Owned-emulator localhost forward")
	device := flag.String("device-certificate", "", "Synthetic public device certificate")
	certificate := flag.String("client-certificate", "", "Synthetic public executor certificate")
	key := flag.String("client-key", "", "Private temporary executor key")
	flag.Parse()
	if os.Getenv("SOVEREIGN_OWNED_EMULATOR") != "1" || flag.NArg() != 0 {
		return errors.New("owned emulator required")
	}
	client, err := tv.NewClient(tv.Profile{Address: "127.0.0.1", Port: *port, DeviceCertificate: *device, ClientCertificate: *certificate, ClientKey: *key}, true)
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
	x, err := tv.New(ctx, tv.Config{Namespace: "owned-emulator-probe", Account: "tv:emulator", Transport: client})
	if err != nil {
		return err
	}
	random := make([]byte, 16)
	if _, err = rand.Read(random); err != nil {
		return err
	}
	in := journal.Intent{ID: hex.EncodeToString(random), Account: "tv:emulator", Executor: tv.Name, Action: tv.ActionApply, Params: map[string]any{"device_id": client.DeviceID(), "base_revision": base, "document": string(encoded)}}
	applied := x.Execute(ctx, in, 1)
	if applied.Result != journal.ResultSucceeded {
		return errors.New("apply unconfirmed")
	}
	if x.Execute(ctx, in, 1) != applied {
		return errors.New("exact retry changed evidence")
	}
	fresh, err := tv.New(ctx, tv.Config{Namespace: "owned-emulator-probe", Account: "tv:emulator", Transport: client})
	if err != nil {
		return err
	}
	if fresh.Reconcile(ctx, in, 1) != applied {
		return errors.New("reconciliation changed evidence")
	}
	revision, current, err := state()
	if err != nil || revision != base+1 || current != string(encoded) {
		return errors.New("readback mismatch")
	}
	if _, err = inspect.Preview(ctx, base, string(encoded)); !errors.Is(err, tv.ErrStaleRevision) {
		return errors.New("stale preview not refused")
	}
	in.ID += "-undo"
	in.Action = tv.ActionUndo
	in.Params = map[string]any{"device_id": client.DeviceID(), "base_revision": base + 1, "restore_revision": base}
	if fresh.Execute(ctx, in, 1).Result != journal.ResultSucceeded {
		return errors.New("undo unconfirmed")
	}
	revision, current, err = state()
	if err != nil || revision != base+2 || current != original {
		return errors.New("undo readback mismatch")
	}
	fmt.Println(`{"go_executor":true,"state_inspection":true,"validation_preview":true,"application_discovery":true,"stale_preview_refused":true,"operation_receipt_verified":true,"reconcile":true,"exact_retry":true,"undo":true,"agentos_qualified":false}`)
	return nil
}
func main() {
	if run() != nil {
		fmt.Fprintln(os.Stderr, "Owned-emulator Go executor qualification failed; no raw evidence printed.")
		os.Exit(1)
	}
}
