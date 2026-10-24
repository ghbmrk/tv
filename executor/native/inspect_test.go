package native

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strings"
	"testing"
	"time"
)

type inspectionTransport struct {
	id       string
	calls    []string
	fields   []map[string]any
	response Response
	err      error
}

func (f *inspectionTransport) DeviceID() string { return f.id }
func (f *inspectionTransport) Request(_ context.Context, op string, fields map[string]any, _ int64) (Response, error) {
	f.calls = append(f.calls, op)
	f.fields = append(f.fields, fields)
	return f.response, f.err
}
func inspector(t *testing.T, result any) (*Inspector, *inspectionTransport) {
	t.Helper()
	f := &inspectionTransport{id: device, response: Response{"ok", raw(result)}}
	x, err := NewInspector(f)
	if err != nil {
		t.Fatal(err)
	}
	return x, f
}
func snapshotWire() map[string]any {
	return map[string]any{"revision": int64(7), "document": document, "document_sha256": digest(document), "recovered_default": false}
}
func TestInspectionVerifiedStateAndNativePreview(t *testing.T) {
	x, f := inspector(t, snapshotWire())
	saved, err := x.State(context.Background())
	if err != nil || saved.DeviceID != device || saved.Revision != 7 || saved.Document != document || saved.DocumentSHA256 != digest(document) || saved.RecoveredDefault || len(f.calls) != 1 || f.calls[0] != "state" || len(f.fields[0]) != 0 {
		t.Fatal("snapshot not verified", err)
	}
	preview := snapshotWire()
	preview["saved"] = false
	preview["displayed_on_tv"] = false
	f.response.Result = raw(preview)
	proposed, err := x.Preview(context.Background(), 7, document)
	if err != nil || proposed != saved || len(f.fields[1]) != 2 || f.fields[1]["base_revision"] != int64(7) || f.fields[1]["document"] != document || strings.Join(f.calls, ",") != "state,preview" {
		t.Fatal("preview changed target/document or sent an effect", err)
	}
}
func TestInspectionRejectsIncompleteAmbiguousOrChangedSnapshots(t *testing.T) {
	for _, kind := range []string{"digest", "missing-recovery", "null-recovery", "zero", "overflow", "fractional", "duplicate", "unknown", "bad-document", "duplicate-document", "large-document", "invalid-utf8"} {
		t.Run(kind, func(t *testing.T) {
			wire := snapshotWire()
			switch kind {
			case "digest":
				wire["document_sha256"] = strings.Repeat("b", 64)
			case "missing-recovery":
				delete(wire, "recovered_default")
			case "null-recovery":
				wire["recovered_default"] = nil
			case "zero":
				wire["revision"] = 0
			case "overflow":
				wire["revision"] = maxExactInteger + 1
			case "fractional":
				wire["revision"] = 7.5
			case "unknown":
				wire["private_error"] = document
			case "bad-document":
				wire["document"] = "[]"
				wire["document_sha256"] = digest("[]")
			case "duplicate-document":
				wire["document"] = `{"x":1,"x":2}`
				wire["document_sha256"] = digest(wire["document"].(string))
			case "large-document":
				wire["document"] = `{"x":"` + strings.Repeat("x", 65536) + `"}`
				wire["document_sha256"] = digest(wire["document"].(string))
			}
			x, f := inspector(t, wire)
			if kind == "duplicate" {
				f.response.Result = append([]byte(`{"revision":7,`), f.response.Result[1:]...)
			}
			if kind == "invalid-utf8" {
				f.response.Result = []byte{0xff}
			}
			got, err := x.State(context.Background())
			if got != (Snapshot{}) || !errors.Is(err, ErrInspection) || strings.Contains(err.Error(), "PRIVATE") || len(f.calls) != 1 {
				t.Fatal("unverified state escaped", kind, err)
			}
		})
	}
}
func TestPreviewRefusesUnboundClaimsAndDoesNotReserveRevision(t *testing.T) {
	for _, kind := range []string{"saved", "displayed", "missing-saved", "missing-displayed", "different-base", "different-document", "recovered", "conflict", "unknown", "transport-error"} {
		t.Run(kind, func(t *testing.T) {
			wire := snapshotWire()
			wire["saved"] = false
			wire["displayed_on_tv"] = false
			switch kind {
			case "saved":
				wire["saved"] = true
			case "displayed":
				wire["displayed_on_tv"] = true
			case "missing-saved":
				delete(wire, "saved")
			case "missing-displayed":
				delete(wire, "displayed_on_tv")
			case "different-base":
				wire["revision"] = 8
			case "different-document":
				wire["document"] = "{}"
				wire["document_sha256"] = digest("{}")
			case "recovered":
				wire["recovered_default"] = true
			}
			x, f := inspector(t, wire)
			expected := ErrInspection
			if kind == "conflict" {
				f.response.Status = "conflict"
				expected = ErrStaleRevision
			}
			if kind == "unknown" {
				f.response.Status = "unknown"
			}
			if kind == "transport-error" {
				f.err = errors.New(document)
			}
			got, err := x.Preview(context.Background(), 7, document)
			if got != (Snapshot{}) || !errors.Is(err, expected) || len(f.calls) != 1 || f.calls[0] != "preview" {
				t.Fatal("unverified preview escaped", err)
			}
		})
	}
}
func TestInspectionRefusesBadRequestsOrChangedTargetsBeforeTransport(t *testing.T) {
	if _, err := NewInspector(nil); err == nil {
		t.Fatal("nil transport")
	}
	for _, p := range []struct {
		base     int64
		document string
	}{{0, document}, {maxExactInteger, document}, {7, "null"}, {7, "\xff"}, {7, `{"x":1,"x":2}`}} {
		x, f := inspector(t, snapshotWire())
		if _, err := x.Preview(context.Background(), p.base, p.document); err == nil || len(f.calls) != 0 {
			t.Fatal("invalid preview dispatched")
		}
	}
	x, f := inspector(t, snapshotWire())
	f.id = strings.Repeat("b", 64)
	if _, err := x.State(context.Background()); err == nil || len(f.calls) != 0 {
		t.Fatal("changed target received query")
	}
	x, f = inspector(t, snapshotWire())
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := x.State(ctx); err == nil || len(f.calls) != 0 {
		t.Fatal("cancelled query dispatched")
	}
	var absent *Inspector
	if _, err := absent.State(context.Background()); err == nil {
		t.Fatal("nil inspector")
	}
}
func catalogWire(apps []Application) map[string]any {
	data := raw(apps)
	return map[string]any{"applications": json.RawMessage(data), "catalog_sha256": digest(string(data)), "truncated": false, "launch_is_playback_qualification": false}
}
func applicationsFixture() []Application {
	return []Application{{"app_" + strings.Repeat("a", 60), "Untrusted TV app", []string{"netflix"}}, {"app_" + strings.Repeat("b", 60), "Local app", []string{}}}
}
func TestCatalogPreservesOpaqueTargetsAndTruncationWithoutPlaybackClaims(t *testing.T) {
	wire := catalogWire(applicationsFixture())
	wire["truncated"] = true
	x, f := inspector(t, wire)
	catalog, err := x.Applications(context.Background())
	if err != nil || catalog.DeviceID != device || !catalog.Truncated || len(catalog.Applications) != 2 || catalog.Applications[0].Target != applicationsFixture()[0].Target || len(catalog.Applications[1].Aliases) != 0 || strings.Join(f.calls, ",") != "apps.list" {
		t.Fatal("catalog failed", err)
	}
	x, _ = inspector(t, catalogWire([]Application{}))
	catalog, err = x.Applications(context.Background())
	if err != nil || len(catalog.Applications) != 0 {
		t.Fatal("empty catalog rejected", err)
	}
}
func TestCatalogRejectsIdentityAmbiguityRawComponentsAndExcessiveData(t *testing.T) {
	for _, kind := range []string{"duplicate-target", "duplicate-alias", "unknown-alias", "component", "empty-title", "long-title", "control-title", "null-aliases", "many-aliases", "null-apps", "missing-truncation", "missing-playback", "playback-claim", "hash", "unknown-field", "duplicate-field", "large"} {
		t.Run(kind, func(t *testing.T) {
			apps := applicationsFixture()
			switch kind {
			case "duplicate-target":
				apps[1].Target = apps[0].Target
			case "duplicate-alias":
				apps[1].Aliases = []string{"netflix"}
			case "unknown-alias":
				apps[0].Aliases = []string{"shell"}
			case "component":
				apps[0].Target = "com.netflix.ninja/.Main"
			case "empty-title":
				apps[0].Title = "  "
			case "long-title":
				apps[0].Title = strings.Repeat("界", 121)
			case "control-title":
				apps[0].Title = "private\napp"
			case "null-aliases":
				apps[0].Aliases = nil
			case "many-aliases":
				apps[0].Aliases = []string{"netflix", "youtube"}
			case "null-apps":
				apps = nil
			case "large":
				apps = make([]Application, 257)
			}
			wire := catalogWire(apps)
			switch kind {
			case "missing-truncation":
				delete(wire, "truncated")
			case "missing-playback":
				delete(wire, "launch_is_playback_qualification")
			case "playback-claim":
				wire["launch_is_playback_qualification"] = true
			case "hash":
				wire["catalog_sha256"] = strings.Repeat("b", 64)
			case "unknown-field":
				wire["screenshot"] = "PRIVATE-CANARY"
			}
			x, f := inspector(t, wire)
			if kind == "duplicate-field" {
				f.response.Result = append([]byte(`{"truncated":false,`), f.response.Result[1:]...)
			}
			got, err := x.Applications(context.Background())
			if !errors.Is(err, ErrInspection) || got.DeviceID != "" || got.Applications != nil || len(f.calls) != 1 {
				t.Fatal("unverified catalog escaped", err)
			}
		})
	}
}
func TestPairedTransportAdmitsOnlyReadPreviewEnvelopes(t *testing.T) {
	for _, op := range []string{"apps.list", "preview"} {
		t.Run(op, func(t *testing.T) {
			client, _, calls := fixtureClient(t, func(c net.Conn, r map[string]any) {
				if r["operation"] != op || (op == "preview" && (r["base_revision"] != float64(7) || r["document"] != document)) {
					t.Error("wrong native query")
				}
				answer(c, r, `{}`)
			}, false)
			fields := map[string]any(nil)
			if op == "preview" {
				fields = map[string]any{"base_revision": int64(7), "document": document}
			}
			if _, err := client.Request(context.Background(), op, fields, time.Now().Add(time.Second).UnixMilli()); err != nil || calls.Load() != 1 {
				t.Fatal("paired query failed", err)
			}
		})
	}
	client, _, calls := fixtureClient(t, func(c net.Conn, r map[string]any) { answer(c, r, `{}`) }, false)
	for _, query := range []struct {
		op     string
		fields map[string]any
	}{{"apps.list", map[string]any{"target": "shell"}}, {"preview", map[string]any{"base_revision": int64(7)}}, {"preview", map[string]any{"base_revision": int64(7), "document": document, "request_id": "effect"}}, {"screen.capture", nil}} {
		if _, err := client.Request(context.Background(), query.op, query.fields, time.Now().Add(time.Second).UnixMilli()); err == nil {
			t.Fatal("unbounded read admitted")
		}
	}
	if calls.Load() != 0 {
		t.Fatal("invalid query connected")
	}
}

func TestTypedDecodingRejectsGoCaseFoldAliasesAtEveryTypedBoundary(t *testing.T) {
	for _, body := range []string{`{"revision":7,"Revision":8}`, `{"Revision":7}`, `{"revision":7,"DOCUMENT":"private"}`} {
		var wire wireSnapshot
		if decodeExact([]byte(body), &wire) {
			t.Fatal("case-folded field admitted")
		}
	}
	var catalog []Application
	if decodeExact([]byte(`[{"Target":"app_a","title":"app","aliases":[]}]`), &catalog) {
		t.Fatal("nested case-fold alias admitted")
	}
	var receipt Receipt
	if decodeExact([]byte(`{"Request_ID":"private"}`), &receipt) {
		t.Fatal("receipt case-fold alias admitted")
	}
	var profile Profile
	if decodeExact([]byte(`{"ADDRESS":"127.0.0.1"}`), &profile) {
		t.Fatal("profile case-fold alias admitted")
	}
	// Keys inside a deliberately opaque RawMessage are validated on typed decode.
	var envelope struct {
		Result json.RawMessage `json:"result"`
	}
	if !decodeExact([]byte(`{"result":{"Revision":7}}`), &envelope) || decodeExact(envelope.Result, new(wireSnapshot)) {
		t.Fatal("opaque boundary misclassified")
	}
}

func TestRequiredCapabilityCannotUseACaseFoldedAlias(t *testing.T) {
	for _, body := range []string{`{"Receipt_Operation_Sha256":true}`, `{"receipt_operation_sha256":true,"RECEIPT_OPERATION_SHA256":false}`} {
		f := &inspectionTransport{id: device, response: Response{"ok", json.RawMessage(body)}}
		if _, err := NewEditor(context.Background(), f); err == nil || len(f.calls) != 1 || f.calls[0] != "capabilities" {
			t.Fatal("ambiguous capability enabled effects")
		}
	}
	f := &inspectionTransport{id: device, response: Response{"ok", json.RawMessage(`{"receipt_operation_sha256":true,"other_known_or_future_capability":true}`)}}
	if _, err := NewEditor(context.Background(), f); err != nil {
		t.Fatal("unrelated additive capabilities refused", err)
	}
}

func TestCatalogAcceptsTheNativeMaximumWithoutLosingTruncation(t *testing.T) {
	apps := make([]Application, 256)
	for i := range apps {
		apps[i] = Application{fmt.Sprintf("app_%060x", i), strings.Repeat("界", 120), []string{}}
	}
	x, _ := inspector(t, catalogWire(apps))
	got, err := x.Applications(context.Background())
	if err != nil || len(got.Applications) != 256 || got.Truncated || got.Applications[255].Target != apps[255].Target {
		t.Fatal("native catalog bound rejected", err)
	}
}
