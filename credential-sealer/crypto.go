package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strings"
)

func decryptEnvelope(secret []byte, envelope string) ([]byte, error) {
	parts := strings.Split(envelope, ":")
	if len(parts) != 4 || parts[0] != "v1" {
		return nil, errDecrypt
	}
	decode := base64.RawURLEncoding.DecodeString
	iv, err := decode(parts[1])
	if err != nil || len(iv) != 12 {
		return nil, errDecrypt
	}
	tag, err := decode(parts[2])
	if err != nil || len(tag) != 16 {
		return nil, errDecrypt
	}
	ciphertext, err := decode(parts[3])
	if err != nil || len(ciphertext) == 0 {
		return nil, errDecrypt
	}
	key := sha256.Sum256(secret)
	block, err := aes.NewCipher(key[:])
	if err != nil {
		return nil, fmt.Errorf("%w", errDecrypt)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("%w", errDecrypt)
	}
	combined := make([]byte, 0, len(ciphertext)+len(tag))
	combined = append(combined, ciphertext...)
	combined = append(combined, tag...)
	plaintext, err := gcm.Open(nil, iv, combined, nil)
	clear(combined)
	if err != nil {
		return nil, errDecrypt
	}
	return plaintext, nil
}
