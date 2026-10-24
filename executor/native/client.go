package native

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"net"
	"net/netip"
	"os"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
	"unicode/utf8"
)

var ErrUnavailable = errors.New("pinned TV transport unavailable; no automatic retry")
var ErrUnconfirmed = errors.New("TV effect unconfirmed; reconcile its original request ID")

type Profile struct {
	Address           string `json:"address"`
	Port              int    `json:"port"`
	DeviceCertificate string `json:"device_certificate"`
	ClientCertificate string `json:"client_certificate"`
	ClientKey         string `json:"client_key"`
}
type Client struct {
	endpoint, device string
	tls              *tls.Config
}

func (c *Client) DeviceID() string { return c.device }

func boundedFile(path string, maximum int, private bool) ([]byte, error) {
	flags := os.O_RDONLY
	if private {
		flags |= syscall.O_NOFOLLOW
	}
	file, err := os.OpenFile(path, flags, 0)
	if err != nil {
		return nil, ErrUnavailable
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > int64(maximum) {
		return nil, ErrUnavailable
	}
	if private {
		stat, ok := info.Sys().(*syscall.Stat_t)
		if !ok || stat.Uid != uint32(os.Getuid()) || info.Mode().Perm()&0o077 != 0 {
			return nil, ErrUnavailable
		}
	}
	data, err := io.ReadAll(io.LimitReader(file, int64(maximum)+1))
	if err != nil || len(data) > maximum {
		return nil, ErrUnavailable
	}
	return data, nil
}

// OpenProfile reads only owner-private local configuration. Emulator loopback is
// explicitly enabled by the owned-emulator qualification driver, never by intent.
func OpenProfile(path string, allowEmulatorLoopback bool) (*Client, error) {
	data, err := boundedFile(path, 16384, true)
	if err != nil {
		return nil, err
	}
	var profile Profile
	if !decodeExact(data, &profile) {
		return nil, ErrUnavailable
	}
	for _, field := range []*string{&profile.DeviceCertificate, &profile.ClientCertificate, &profile.ClientKey} {
		if !filepath.IsAbs(*field) {
			*field = filepath.Join(filepath.Dir(path), *field)
		}
	}
	return NewClient(profile, allowEmulatorLoopback)
}
func NewClient(profile Profile, allowEmulatorLoopback bool) (*Client, error) {
	address, err := netip.ParseAddr(profile.Address)
	if err != nil || !address.Is4() || (!address.IsPrivate() && !(allowEmulatorLoopback && address.IsLoopback())) || profile.Port < 1 || profile.Port > 65535 {
		return nil, ErrUnavailable
	}
	serverPEM, err := boundedFile(profile.DeviceCertificate, 16384, false)
	if err != nil {
		return nil, err
	}
	block, rest := pem.Decode(serverPEM)
	if !bytes.HasPrefix(bytes.TrimSpace(serverPEM), []byte("-----BEGIN CERTIFICATE-----")) || block == nil || block.Type != "CERTIFICATE" || len(block.Headers) != 0 || len(bytes.TrimSpace(rest)) != 0 {
		return nil, ErrUnavailable
	}
	server, err := x509.ParseCertificate(block.Bytes)
	if err != nil || !bytes.Equal(server.RawIssuer, server.RawSubject) || server.CheckSignature(server.SignatureAlgorithm, server.RawTBSCertificate, server.Signature) != nil {
		return nil, ErrUnavailable
	}
	switch key := server.PublicKey.(type) {
	case *ecdsa.PublicKey:
		if bits := key.Curve.Params().BitSize; bits != 256 && bits != 384 {
			return nil, ErrUnavailable
		}
	case *rsa.PublicKey:
		if bits := key.N.BitLen(); bits < 2048 || bits > 4096 {
			return nil, ErrUnavailable
		}
	default:
		return nil, ErrUnavailable
	}
	clientPEM, err := boundedFile(profile.ClientCertificate, 16384, false)
	if err != nil {
		return nil, err
	}
	keyPEM, err := boundedFile(profile.ClientKey, 65536, true)
	if err != nil {
		return nil, err
	}
	identity, err := tls.X509KeyPair(clientPEM, keyPEM)
	if err != nil {
		return nil, ErrUnavailable
	}
	pin := sha256.Sum256(server.Raw)
	roots := x509.NewCertPool()
	roots.AddCert(server)
	config := &tls.Config{MinVersion: tls.VersionTLS12, Certificates: []tls.Certificate{identity},
		// LAN addresses change and the self-signed identity has no address SAN. The
		// replacement verifier below checks the exact DER pin AND normal X.509 validity.
		InsecureSkipVerify: true, VerifyConnection: func(state tls.ConnectionState) error {
			if len(state.PeerCertificates) != 1 || sha256.Sum256(state.PeerCertificates[0].Raw) != pin {
				return ErrUnavailable
			}
			_, err := state.PeerCertificates[0].Verify(x509.VerifyOptions{Roots: roots, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}})
			if err != nil {
				return ErrUnavailable
			}
			return nil
		}}
	return &Client{net.JoinHostPort(address.String(), strconv.Itoa(profile.Port)), hex.EncodeToString(pin[:]), config}, nil
}
func readFrame(reader io.Reader) ([]byte, error) {
	var size uint32
	if err := binary.Read(reader, binary.BigEndian, &size); err != nil {
		return nil, err
	}
	if size == 0 || size > 512*1024 {
		return nil, ErrUnavailable
	}
	data := make([]byte, int(size))
	_, err := io.ReadFull(reader, data)
	return data, err
}
func writeFrame(writer io.Writer, data []byte) error {
	if len(data) == 0 || len(data) > 512*1024 {
		return ErrUnavailable
	}
	frame := make([]byte, 4+len(data))
	binary.BigEndian.PutUint32(frame, uint32(len(data)))
	copy(frame[4:], data)
	for len(frame) > 0 {
		n, err := writer.Write(frame)
		if err != nil {
			return err
		}
		if n <= 0 {
			return io.ErrShortWrite
		}
		frame = frame[n:]
	}
	return nil
}
func (c *Client) Request(ctx context.Context, operation string, fields map[string]any, expires int64) (result Response, failure error) {
	required := map[string][]string{"capabilities": {}, "state": {}, "apps.list": {}, "preview": {"base_revision", "document"}, "receipt": {"request_id"}, "apply": {"request_id", "base_revision", "document"}, "undo": {"request_id", "base_revision", "restore_revision"}}
	expected, ok := required[operation]
	if !ok || len(fields) != len(expected) || ctx.Err() != nil || expires <= time.Now().UnixMilli() || expires > time.Now().Add(30*time.Second).UnixMilli() {
		return Response{}, ErrUnavailable
	}
	envelope := map[string]any{"v": 1, "device_id": c.device, "operation": operation, "expires_at_ms": expires}
	for _, key := range expected {
		value, ok := fields[key]
		if !ok {
			return Response{}, ErrUnavailable
		}
		switch v := value.(type) {
		case string:
			if !utf8.ValidString(v) {
				return Response{}, ErrUnavailable
			}
		case int64:
		case int:
		default:
			return Response{}, ErrUnavailable
		}
		envelope[key] = value
	}
	data, err := json.Marshal(envelope)
	if err != nil || len(data) > 512*1024 {
		return Response{}, ErrUnavailable
	}
	effect := operation == "apply" || operation == "undo"
	attempted := false
	defer func() {
		if failure != nil {
			if effect && attempted {
				failure = ErrUnconfirmed
			} else {
				failure = ErrUnavailable
			}
		}
	}()
	raw, err := (&net.Dialer{Timeout: 5 * time.Second}).DialContext(ctx, "tcp4", c.endpoint)
	if err != nil {
		return Response{}, err
	}
	defer raw.Close()
	stop := context.AfterFunc(ctx, func() { raw.Close() })
	defer stop()
	connection := tls.Client(raw, c.tls)
	handshake, cancel := context.WithTimeout(ctx, 5*time.Second)
	err = connection.HandshakeContext(handshake)
	cancel()
	if err != nil {
		return Response{}, err
	}
	deadline := time.Now().Add(40 * time.Second)
	if until, ok := ctx.Deadline(); ok && until.Before(deadline) {
		deadline = until
	}
	if err = connection.SetDeadline(deadline); err != nil {
		return Response{}, err
	}
	attempted = true
	if err = writeFrame(connection, data); err != nil {
		return Response{}, err
	}
	body, err := readFrame(connection)
	if err != nil {
		return Response{}, err
	}
	var response struct {
		Version int             `json:"v"`
		Device  string          `json:"device_id"`
		Status  string          `json:"status"`
		Result  json.RawMessage `json:"result"`
	}
	if !decodeExact(body, &response) || response.Version != 1 || response.Device != c.device || response.Status == "" {
		return Response{}, ErrUnavailable
	}
	return Response{response.Status, response.Result}, nil
}
