package native

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// Edit names one exact native operation. RequestID is assigned by the trusted
// embedding, never by an experience document or device response.
type Edit struct {
	RequestID       string `json:"request_id"`
	Operation       string `json:"operation"`
	BaseRevision    int64  `json:"base_revision"`
	Document        string `json:"document,omitempty"`
	RestoreRevision int64  `json:"restore_revision,omitempty"`
}

type Outcome struct {
	Status  string // committed, refused or unknown
	Receipt *Receipt
}

// Editor has no broker authority. Its caller must authorize each dispatch and
// preserve uncertainty across restart. Reconcile never resends an edit.
type Editor struct {
	transport Transport
	device    string
}

func NewEditor(ctx context.Context, transport Transport) (*Editor, error) {
	if transport == nil || !hexDigest.MatchString(transport.DeviceID()) {
		return nil, errors.New("invalid pinned TV transport")
	}
	device := transport.DeviceID()
	response, err := transport.Request(ctx, "capabilities", nil, expiry(ctx))
	var caps map[string]json.RawMessage
	var supported bool
	if err != nil || ctx.Err() != nil || transport.DeviceID() != device || response.Status != "ok" ||
		!uniqueJSON(response.Result) || json.Unmarshal(response.Result, &caps) != nil ||
		json.Unmarshal(caps["receipt_operation_sha256"], &supported) != nil || !supported {
		return nil, errors.New("TV receipt verification capability unavailable")
	}
	for key := range caps {
		if key != "receipt_operation_sha256" && strings.EqualFold(key, "receipt_operation_sha256") {
			return nil, errors.New("ambiguous TV capability")
		}
	}
	return &Editor{transport: transport, device: device}, nil
}

func (x *Editor) DeviceID() string { return x.device }

func ValidateEdit(edit Edit) bool {
	if !hexDigest.MatchString(edit.RequestID) || edit.BaseRevision < 1 || edit.BaseRevision >= maxExactInteger {
		return false
	}
	switch edit.Operation {
	case "apply":
		return edit.RestoreRevision == 0 && len(edit.Document) <= 65536 &&
			bytes.HasPrefix(bytes.TrimSpace([]byte(edit.Document)), []byte("{")) && uniqueJSON([]byte(edit.Document))
	case "undo":
		return edit.Document == "" && edit.RestoreRevision > 0 && edit.RestoreRevision < edit.BaseRevision
	}
	return false
}

func verified(edit Edit, raw json.RawMessage) Outcome {
	var receipt Receipt
	fingerprint := fmt.Sprintf("undo:%d:%d", edit.BaseRevision, edit.RestoreRevision)
	if edit.Operation == "apply" {
		fingerprint = fmt.Sprintf("apply:%d:%s", edit.BaseRevision, hash(edit.Document))
	}
	if !decodeExact(raw, &receipt) || receipt.RequestID != edit.RequestID ||
		receipt.PreviousRevision != edit.BaseRevision || receipt.Revision != edit.BaseRevision+1 ||
		!hexDigest.MatchString(receipt.DocumentSHA256) || receipt.OperationSHA256 != hash(fingerprint) ||
		(edit.Operation == "apply" && receipt.DocumentSHA256 != hash(edit.Document)) {
		return Outcome{Status: "unknown"}
	}
	return Outcome{Status: "committed", Receipt: &receipt}
}

func (x *Editor) Execute(ctx context.Context, edit Edit) Outcome {
	if x == nil || ctx.Err() != nil || x.transport.DeviceID() != x.device || !ValidateEdit(edit) {
		return Outcome{Status: "refused"}
	}
	fields := map[string]any{"request_id": edit.RequestID, "base_revision": edit.BaseRevision}
	if edit.Operation == "apply" {
		fields["document"] = edit.Document
	} else {
		fields["restore_revision"] = edit.RestoreRevision
	}
	response, err := x.transport.Request(ctx, edit.Operation, fields, expiry(ctx))
	if err != nil || x.transport.DeviceID() != x.device {
		return Outcome{Status: "unknown"}
	}
	if response.Status == "ok" {
		var body struct {
			Receipt json.RawMessage `json:"receipt"`
			State   json.RawMessage `json:"state"`
		}
		if !decodeExact(response.Result, &body) {
			return Outcome{Status: "unknown"}
		}
		return verified(edit, body.Receipt)
	}
	switch response.Status {
	case "invalid", "expired", "unauthorized", "conflict", "capacity":
		return Outcome{Status: "refused"}
	}
	return Outcome{Status: "unknown"}
}

func (x *Editor) Reconcile(ctx context.Context, edit Edit) Outcome {
	if x == nil || ctx.Err() != nil || x.transport.DeviceID() != x.device || !ValidateEdit(edit) {
		return Outcome{Status: "unknown"}
	}
	response, err := x.transport.Request(ctx, "receipt", map[string]any{"request_id": edit.RequestID}, expiry(ctx))
	if err != nil || x.transport.DeviceID() != x.device || response.Status != "ok" {
		return Outcome{Status: "unknown"}
	}
	return verified(edit, response.Result)
}
