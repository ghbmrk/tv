package executor

import "github.com/ghbmrk/tv/executor/native"

type Profile = native.Profile
type Client = native.Client

var ErrUnavailable = native.ErrUnavailable
var ErrUnconfirmed = native.ErrUnconfirmed
var OpenProfile = native.OpenProfile
var NewClient = native.NewClient
