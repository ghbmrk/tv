package executor

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func certificate(t *testing.T, usage x509.ExtKeyUsage) (tls.Certificate, []byte, []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(time.Now().UnixNano()), Subject: pkix.Name{CommonName: "Synthetic executor fixture"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{usage}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	keyDER, _ := x509.MarshalPKCS8PrivateKey(key)
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER})
	pair, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		t.Fatal(err)
	}
	return pair, certPEM, keyPEM
}
func fixtureClient(t *testing.T, serve func(net.Conn, map[string]any), wrongPin bool) (*Client, Profile, *atomic.Int32) {
	t.Helper()
	server, serverPEM, _ := certificate(t, x509.ExtKeyUsageServerAuth)
	_, clientPEM, keyPEM := certificate(t, x509.ExtKeyUsageClientAuth)
	roots := x509.NewCertPool()
	roots.AppendCertsFromPEM(clientPEM)
	listener, err := tls.Listen("tcp4", "127.0.0.1:0", &tls.Config{Certificates: []tls.Certificate{server}, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: roots, MinVersion: tls.VersionTLS12})
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	calls := new(atomic.Int32)
	go func() {
		defer close(done)
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		defer connection.Close()
		connection.SetDeadline(time.Now().Add(2 * time.Second))
		bytes, err := readFrame(connection)
		if err != nil {
			return
		}
		var request map[string]any
		if json.Unmarshal(bytes, &request) != nil {
			return
		}
		calls.Add(1)
		serve(connection, request)
	}()
	t.Cleanup(func() {
		listener.Close()
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			t.Error("fixture socket did not terminate")
		}
	})
	dir := t.TempDir()
	if wrongPin {
		_, serverPEM, _ = certificate(t, x509.ExtKeyUsageServerAuth)
	}
	files := map[string][]byte{"device.pem": serverPEM, "client.pem": clientPEM, "key.pem": keyPEM}
	for name, data := range files {
		if err := os.WriteFile(filepath.Join(dir, name), data, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	host, port, _ := net.SplitHostPort(listener.Addr().String())
	number, _ := strconv.Atoi(port)
	profile := Profile{Address: host, Port: number, DeviceCertificate: filepath.Join(dir, "device.pem"), ClientCertificate: filepath.Join(dir, "client.pem"), ClientKey: filepath.Join(dir, "key.pem")}
	client, err := NewClient(profile, true)
	if err != nil {
		t.Fatal(err)
	}
	return client, profile, calls
}
func answer(connection net.Conn, request map[string]any, result string) {
	body := []byte(`{"v":1,"device_id":"` + request["device_id"].(string) + `","status":"ok","result":` + result + `}`)
	writeFrame(connection, body)
}
func TestPinnedMutualTLSAndContextCancellation(t *testing.T) {
	client, _, calls := fixtureClient(t, func(c net.Conn, r map[string]any) { answer(c, r, `{"revision":1}`) }, false)
	response, err := client.Request(context.Background(), "state", nil, time.Now().Add(time.Second).UnixMilli())
	if err != nil || response.Status != "ok" || string(response.Result) != `{"revision":1}` || calls.Load() != 1 {
		t.Fatal(response, err, calls.Load())
	}
	slow, _, _ := fixtureClient(t, func(c net.Conn, _ map[string]any) { io.Copy(io.Discard, c) }, false)
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, err = slow.Request(ctx, "state", nil, time.Now().Add(time.Second).UnixMilli())
	if !errors.Is(err, ErrUnavailable) || time.Since(started) > time.Second {
		t.Fatal("cancel did not bound input", err)
	}
}
func TestChangedDeviceCannotReceiveApplicationData(t *testing.T) {
	client, _, calls := fixtureClient(t, func(c net.Conn, r map[string]any) { answer(c, r, `{}`) }, true)
	if _, err := client.Request(context.Background(), "state", nil, time.Now().Add(time.Second).UnixMilli()); !errors.Is(err, ErrUnavailable) || calls.Load() != 0 {
		t.Fatal("changed device admitted", err)
	}
}
func TestLostEffectReplyIsUnknownWithoutRetry(t *testing.T) {
	client, _, calls := fixtureClient(t, func(net.Conn, map[string]any) {}, false)
	_, err := client.Request(context.Background(), "apply", map[string]any{"request_id": strings.Repeat("a", 64), "base_revision": int64(1), "document": "{}"}, time.Now().Add(time.Second).UnixMilli())
	if !errors.Is(err, ErrUnconfirmed) || calls.Load() != 1 {
		t.Fatal("effect loss misclassified or replayed", err, calls.Load())
	}
}
func TestAmbiguousOversizedOrBinaryResponsesAreRefused(t *testing.T) {
	for _, kind := range []string{"duplicate", "oversized", "binary"} {
		t.Run(kind, func(t *testing.T) {
			client, _, _ := fixtureClient(t, func(c net.Conn, r map[string]any) {
				switch kind {
				case "oversized":
					binary.Write(c, binary.BigEndian, uint32(512*1024+1))
				case "duplicate":
					writeFrame(c, []byte(`{"v":1,"v":2,"device_id":"`+r["device_id"].(string)+`","status":"ok"}`))
				case "binary":
					writeFrame(c, []byte(`{"v":1,"device_id":"`+r["device_id"].(string)+`","status":"ok","blob_bytes":1}`))
				}
			}, false)
			if _, err := client.Request(context.Background(), "state", nil, time.Now().Add(time.Second).UnixMilli()); !errors.Is(err, ErrUnavailable) {
				t.Fatal(err)
			}
		})
	}
}
func TestPrivateEndpointKeyAndEnvelopeAreOwnerConfiguration(t *testing.T) {
	client, profile, calls := fixtureClient(t, func(c net.Conn, r map[string]any) { answer(c, r, `{}`) }, false)
	for _, args := range []map[string]any{{"operation": "apply"}, {"document": "\xff"}} {
		if _, err := client.Request(context.Background(), "state", args, time.Now().Add(time.Second).UnixMilli()); err == nil {
			t.Fatal("invalid request admitted")
		}
	}
	if calls.Load() != 0 {
		t.Fatal("invalid envelope connected")
	}
	if _, err := NewClient(profile, false); err == nil {
		t.Fatal("implicit loopback admitted")
	}
	profile.Address = "8.8.8.8"
	if _, err := NewClient(profile, true); err == nil {
		t.Fatal("public endpoint admitted")
	}
	profile.Address = "127.0.0.1"
	os.Chmod(profile.ClientKey, 0o644)
	if _, err := NewClient(profile, true); err == nil {
		t.Fatal("public key file admitted")
	}
	os.Chmod(profile.ClientKey, 0o600)
	profile.ClientKey = profile.ClientCertificate
	if _, err := NewClient(profile, true); err == nil {
		t.Fatal("certificate used as private key")
	}
}

func TestPrivateProfileCannotOverrideEndpointPolicyOrContainAmbiguousFields(t *testing.T) {
	_, profile, calls := fixtureClient(t, func(c net.Conn, r map[string]any) { answer(c, r, `{}`) }, false)
	path := filepath.Join(t.TempDir(), "profile.json")
	encoded, _ := json.Marshal(profile)
	if err := os.WriteFile(path, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenProfile(path, true); err != nil {
		t.Fatal(err)
	}
	for _, suffix := range []string{`,"address":"8.8.8.8"}`, `,"allow_loopback":true}`} {
		data := append(append([]byte{}, encoded[:len(encoded)-1]...), []byte(suffix)...)
		os.WriteFile(path, data, 0o600)
		if _, err := OpenProfile(path, true); err == nil {
			t.Fatal("ambiguous profile admitted")
		}
	}
	os.WriteFile(path, encoded, 0o600)
	os.Chmod(path, 0o644)
	if _, err := OpenProfile(path, true); err == nil {
		t.Fatal("public profile admitted")
	}
	if calls.Load() != 0 {
		t.Fatal("configuration validation connected")
	}
}
