//go:build linux

// Package kernelclerk binds native TV configuration to agentOS's current
// signed-plan clerk boundary. It is not a guest endpoint or broker registration.
package kernelclerk

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"regexp"
	"time"
	"unicode/utf8"

	"github.com/ghbmrk/agentos/broker/clerk"
	"github.com/ghbmrk/agentos/broker/kernel"
	"github.com/ghbmrk/agentos/broker/kernel/key"
	"github.com/ghbmrk/tv/executor/internal/wire"
	"github.com/ghbmrk/tv/executor/native"
)

const Label = "tv.configuration"

var localName = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)

// Config is trusted owner embedding configuration, never a plan argument.
// Audience and visibility must come from the qualified device declaration.
// Unknown/cloud-visible devices and public audiences are not supported here.
type Config struct {
	Name, Namespace, Audience, Visibility string
	Anchors                               []ed25519.PublicKey
	Transport                             native.Transport
	Clock                                 clerk.Clock
}

type Clerk struct {
	name, namespace, audience, target string
	anchors                           []ed25519.PublicKey
	clock                             clerk.Clock
	editor                            *native.Editor
}

var _ kernel.Clerk = (*Clerk)(nil)

func New(ctx context.Context, cfg Config) (*Clerk, error) {
	class, known := key.ClassOf(key.ChangeAccount)
	if !known || class != key.IrreversibleHigh || !localName.MatchString(cfg.Name) ||
		!localName.MatchString(cfg.Namespace) || (cfg.Audience != "owner" && cfg.Audience != "household") ||
		cfg.Visibility != "local-only" || len(cfg.Anchors) == 0 || len(cfg.Anchors) > 8 {
		return nil, errors.New("invalid owner TV clerk declaration")
	}
	anchors, seen := make([]ed25519.PublicKey, 0, len(cfg.Anchors)), map[string]bool{}
	for _, anchor := range cfg.Anchors {
		if len(anchor) != ed25519.PublicKeySize || seen[string(anchor)] {
			return nil, errors.New("invalid owner TV trust anchors")
		}
		seen[string(anchor)] = true
		anchors = append(anchors, append(ed25519.PublicKey(nil), anchor...))
	}
	editor, err := native.NewEditor(ctx, cfg.Transport)
	if err != nil {
		return nil, err
	}
	return &Clerk{cfg.Name, cfg.Namespace, cfg.Audience, "tv:" + editor.DeviceID(), anchors, cfg.Clock, editor}, nil
}

func (c *Clerk) Target() string { return c.target }

// Facts conservatively labels the entire configuration private, including
// preferences. No planner claim can reclassify it as public or unlabeled.
func (c *Clerk) Facts(key.Step) (string, []string, int64) {
	return "private", []string{Label}, 0
}

// Command is the complete declared value shape for configuration only. It has
// no endpoint, request ID, credential, arbitrary intent or executable content.
type Command struct {
	Operation       string `json:"operation"`
	BaseRevision    int64  `json:"base_revision"`
	Document        string `json:"document,omitempty"`
	RestoreRevision int64  `json:"restore_revision,omitempty"`
}

func (c *Clerk) prepare(r kernel.Request) (native.Edit, bool) {
	if c == nil || r.Plan.ID == "" || len(r.Plan.ID) > 256 || !utf8.ValidString(r.Plan.ID) ||
		len(r.Plan.Sig) != ed25519.SignatureSize || r.Index < 0 || r.Index >= len(r.Plan.Steps) || len(r.Plan.Steps) > kernel.MaxSteps {
		return native.Edit{}, false
	}
	s := r.Step()
	if s.Clerk != c.name || s.Verb != key.ChangeAccount || len(s.Args) != 2 ||
		s.Args["target"].Value != c.target || s.Recipient != c.target {
		return native.Edit{}, false
	}
	value := s.Args["value"].Value
	var command Command
	if len(value) > 400*1024 || !wire.DecodeExact([]byte(value), &command) {
		return native.Edit{}, false
	}
	encoded, _ := json.Marshal([]string{"sovereign-tv/kernel-v1", c.namespace, c.name, c.target, r.Idem(), hex.EncodeToString(r.Plan.Sig)})
	digest := sha256.Sum256(encoded)
	edit := native.Edit{RequestID: hex.EncodeToString(digest[:]), Operation: command.Operation,
		BaseRevision: command.BaseRevision, Document: command.Document, RestoreRevision: command.RestoreRevision}
	return edit, native.ValidateEdit(edit)
}

// Take an owned snapshot before authorization or a clock/view callback. This
// keeps the selected edit tied to the exact signed plan that was checked.
func freeze(r kernel.Request) (kernel.Request, bool) {
	if len(r.Plan.Steps) == 0 || len(r.Plan.Steps) > kernel.MaxSteps || !utf8.ValidString(r.Plan.ID) {
		return kernel.Request{}, false
	}
	for _, step := range r.Plan.Steps {
		if !utf8.ValidString(string(step.Verb)) || !utf8.ValidString(step.Clerk) || !utf8.ValidString(step.Content) {
			return kernel.Request{}, false
		}
		for name, value := range step.Args {
			if !utf8.ValidString(name) || !utf8.ValidString(value) {
				return kernel.Request{}, false
			}
		}
		for _, label := range step.Labels {
			if !utf8.ValidString(label) {
				return kernel.Request{}, false
			}
		}
	}
	data, err := json.Marshal(r)
	var owned kernel.Request
	if err != nil || !wire.DecodeExact(data, &owned) {
		return kernel.Request{}, false
	}
	return owned, true
}

func answer(out native.Outcome, probe bool) kernel.Result {
	if out.Status == "committed" {
		status := "ok"
		if probe {
			status = "done"
		}
		return kernel.Result{Outcome: status, Detail: "TV configuration commit verified; display state unconfirmed"}
	}
	if out.Status == "refused" && !probe {
		return kernel.Result{Outcome: "failed", Detail: "TV configuration dispatch refused"}
	}
	return kernel.Result{Outcome: "unknown", Detail: "No matching TV receipt; no automatic effect replay"}
}

func (c *Clerk) Do(r kernel.Request, view kernel.View) kernel.Result {
	var snapOK bool
	r, snapOK = freeze(r)
	edit, ok := c.prepare(r)
	if !snapOK || !ok || view == nil {
		return kernel.Result{Outcome: "failed", Detail: "TV configuration shape or target refused"}
	}
	verified, refusal := clerk.Verify(c.anchors, c.name, c.Facts, c.clock.Now(), r, view)
	if refusal != nil {
		return kernel.Result{Outcome: "failed", Detail: "TV authority recheck refused"}
	}
	// A household screen discloses private curation. Until a reviewed template
	// route exists, only an owner-signed exact plan (bare passkey root) covers
	// it. A reusable delegated configuration key is not disclosure authority.
	if c.audience == "household" && len(verified.Key.Links) != 0 {
		return kernel.Result{Outcome: "failed", Detail: "Household presentation needs an owner-signed exact plan"}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return answer(c.editor.Execute(ctx, edit), false)
}

func (c *Clerk) Probe(r kernel.Request, view kernel.View) kernel.Result {
	var snapOK bool
	r, snapOK = freeze(r)
	edit, ok := c.prepare(r)
	if !snapOK || !ok || view == nil {
		return kernel.Result{Outcome: "unknown", Detail: "TV reconciliation shape or target refused"}
	}
	// Reconciliation outlives STOP, revocation and expiry. Verify the signed
	// plan and this clerk's scope, but grant no fresh effect authority here.
	verified, err := kernel.VerifyPlan(r.Plan, kernel.PlanOwners(view, c.anchors, r.Plan.Key))
	if err != nil || verified.Limits.Clerk != c.name {
		return kernel.Result{Outcome: "unknown", Detail: "TV reconciliation signature refused"}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	// Absence never proves non-application; returning notdone could cause a
	// replay. Only a matching native receipt can settle this step as done.
	return answer(c.editor.Reconcile(ctx, edit), true)
}
