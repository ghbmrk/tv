package executor

import "github.com/ghbmrk/tv/executor/native"

type Inspector = native.Inspector
type Snapshot = native.Snapshot
type Application = native.Application
type ApplicationCatalog = native.ApplicationCatalog

var ErrInspection = native.ErrInspection
var ErrStaleRevision = native.ErrStaleRevision
var NewInspector = native.NewInspector
