package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// Inspection data contains private, untrusted household/app content. The owner
// broker must authorize and route it before disclosure. This is not a guest tool,
// capture endpoint, grant checker, current-screen observation or playback proof.
type Inspector struct {
	transport Transport
	device    string
}

var ErrInspection = errors.New("TV inspection unavailable; no content disclosed in error")
var ErrStaleRevision = errors.New("TV preview base changed; read and rebase")
var appTarget = regexp.MustCompile(`^app_[a-f0-9]{60}$`)
var appAliases = map[string]bool{"netflix": true, "prime_video": true, "disney_plus": true, "youtube": true, "hulu": true, "apple_tv": true, "local_control": true}

// NewInspector takes an owner-configured paired transport. No connection, effect,
// capability grant or broker registration is performed by construction.
func NewInspector(transport Transport) (*Inspector, error) {
	if transport == nil || !hexDigest.MatchString(transport.DeviceID()) {
		return nil, ErrInspection
	}
	return &Inspector{transport, transport.DeviceID()}, nil
}

type Snapshot struct {
	DeviceID         string
	Revision         int64
	Document         string
	DocumentSHA256   string
	RecoveredDefault bool
}
type Application struct {
	Target  string   `json:"target"`
	Title   string   `json:"title"`
	Aliases []string `json:"aliases"`
}
type ApplicationCatalog struct {
	DeviceID      string
	Applications  []Application
	Truncated     bool
	CatalogSHA256 string
}
type wireSnapshot struct {
	Revision         int64  `json:"revision"`
	Document         string `json:"document"`
	DocumentSHA256   string `json:"document_sha256"`
	RecoveredDefault *bool  `json:"recovered_default"`
}

func observationDocument(document string) bool {
	return len(document) <= 65536 && utf8.ValidString(document) && bytes.HasPrefix(bytes.TrimSpace([]byte(document)), []byte("{")) && uniqueJSON([]byte(document))
}
func (x *Inspector) request(ctx context.Context, operation string, fields map[string]any) (Response, error) {
	if x == nil || ctx.Err() != nil || x.transport.DeviceID() != x.device {
		return Response{}, ErrInspection
	}
	response, err := x.transport.Request(ctx, operation, fields, expiry(ctx))
	if err != nil || ctx.Err() != nil {
		return Response{}, ErrInspection
	}
	return response, nil
}
func (x *Inspector) snapshot(w wireSnapshot) (Snapshot, error) {
	if w.Revision < 1 || w.Revision > maxExactInteger || w.RecoveredDefault == nil || !observationDocument(w.Document) || !hexDigest.MatchString(w.DocumentSHA256) || hash(w.Document) != w.DocumentSHA256 {
		return Snapshot{}, ErrInspection
	}
	return Snapshot{x.device, w.Revision, w.Document, w.DocumentSHA256, *w.RecoveredDefault}, nil
}

// State reads a durable configuration snapshot. It does not claim that Home is
// visible, that an unsaved preview is displayed, or that a provider is playing.
func (x *Inspector) State(ctx context.Context) (Snapshot, error) {
	response, err := x.request(ctx, "state", nil)
	if err != nil || response.Status != "ok" {
		return Snapshot{}, ErrInspection
	}
	var wire wireSnapshot
	if !decodeExact(response.Result, &wire) {
		return Snapshot{}, ErrInspection
	}
	return x.snapshot(wire)
}

// Preview asks the native validator about this exact document and base. It does
// not save or display it, reserve the revision or authorize a subsequent apply.
// Apply must still check the original base through the journal executor.
func (x *Inspector) Preview(ctx context.Context, base int64, document string) (Snapshot, error) {
	if base < 1 || base >= maxExactInteger || !observationDocument(document) {
		return Snapshot{}, ErrInspection
	}
	response, err := x.request(ctx, "preview", map[string]any{"base_revision": base, "document": document})
	if err != nil {
		return Snapshot{}, ErrInspection
	}
	if response.Status == "conflict" {
		return Snapshot{}, ErrStaleRevision
	}
	if response.Status != "ok" {
		return Snapshot{}, ErrInspection
	}
	var wire struct {
		wireSnapshot
		Saved     *bool `json:"saved"`
		Displayed *bool `json:"displayed_on_tv"`
	}
	if !decodeExact(response.Result, &wire) || wire.Saved == nil || *wire.Saved || wire.Displayed == nil || *wire.Displayed || wire.Revision != base || wire.Document != document || wire.RecoveredDefault == nil || *wire.RecoveredDefault {
		return Snapshot{}, ErrInspection
	}
	return x.snapshot(wire.wireSnapshot)
}

// Applications returns discovered opaque targets, not components/intents or a
// provider compatibility guarantee. Truncation is preserved for the caller.
func (x *Inspector) Applications(ctx context.Context) (ApplicationCatalog, error) {
	response, err := x.request(ctx, "apps.list", nil)
	if err != nil || response.Status != "ok" {
		return ApplicationCatalog{}, ErrInspection
	}
	var wire struct {
		Applications  json.RawMessage `json:"applications"`
		Truncated     *bool           `json:"truncated"`
		CatalogSHA256 string          `json:"catalog_sha256"`
		Playback      *bool           `json:"launch_is_playback_qualification"`
	}
	if !decodeExact(response.Result, &wire) || wire.Truncated == nil || wire.Playback == nil || *wire.Playback || !hexDigest.MatchString(wire.CatalogSHA256) || hash(string(wire.Applications)) != wire.CatalogSHA256 {
		return ApplicationCatalog{}, ErrInspection
	}
	var applications []Application
	if !decodeExact(wire.Applications, &applications) || applications == nil || len(applications) > 256 {
		return ApplicationCatalog{}, ErrInspection
	}
	targets, aliases := map[string]bool{}, map[string]bool{}
	for _, app := range applications {
		if !appTarget.MatchString(app.Target) || targets[app.Target] || !utf8.ValidString(app.Title) || strings.TrimSpace(app.Title) == "" || utf8.RuneCountInString(app.Title) > 120 || strings.ContainsFunc(app.Title, unicode.IsControl) || app.Aliases == nil || len(app.Aliases) > 1 {
			return ApplicationCatalog{}, ErrInspection
		}
		targets[app.Target] = true
		for _, alias := range app.Aliases {
			if !appAliases[alias] || aliases[alias] {
				return ApplicationCatalog{}, ErrInspection
			}
			aliases[alias] = true
		}
	}
	return ApplicationCatalog{x.device, applications, *wire.Truncated, wire.CatalogSHA256}, nil
}
