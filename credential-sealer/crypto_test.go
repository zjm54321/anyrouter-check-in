package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/base64"
	"testing"
)

func TestDecryptMetapiEnvelope(t *testing.T) {
	secret := []byte("dedicated-secret")
	key := sha256.Sum256(secret)
	block, _ := aes.NewCipher(key[:])
	gcm, _ := cipher.NewGCM(block)
	iv := []byte("123456789012")
	combined := gcm.Seal(nil, iv, []byte("p@ss"), nil)
	tag, ciphertext := combined[len(combined)-gcm.Overhead():], combined[:len(combined)-gcm.Overhead()]
	b64 := base64.RawURLEncoding.EncodeToString
	envelope := "v1:" + b64(iv) + ":" + b64(tag) + ":" + b64(ciphertext)
	got, err := decryptEnvelope(secret, envelope)
	if err != nil || string(got) != "p@ss" {
		t.Fatalf("decrypt = %q, %v", got, err)
	}
	for _, bad := range []string{"bad", "v1:AA:AA:AA", "v2:" + b64(iv) + ":" + b64(tag) + ":" + b64(ciphertext)} {
		if _, err := decryptEnvelope(secret, bad); err == nil {
			t.Errorf("malformed %q accepted", bad)
		}
	}
	if _, err := decryptEnvelope([]byte("wrong"), envelope); err == nil {
		t.Fatal("wrong key accepted")
	}
	tag[0] ^= 1
	if _, err := decryptEnvelope(secret, "v1:"+b64(iv)+":"+b64(tag)+":"+b64(ciphertext)); err == nil {
		t.Fatal("bad tag accepted")
	}
}
