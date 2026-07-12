package main

import (
	"bytes"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"strings"

	ssv1alpha1 "github.com/bitnami-labs/sealed-secrets/pkg/apis/sealedsecrets/v1alpha1"
	"github.com/bitnami-labs/sealed-secrets/pkg/kubeseal"
)

type strictEncryptor struct{ publicKey *rsa.PublicKey }

func loadCertificate(path string) (*rsa.PublicKey, error) {
	return loadCertificateWithHash(path, certificateSHA256)
}

func loadCertificateWithHash(path, expectedHash string) (*rsa.PublicKey, error) {
	contents, err := os.ReadFile(path)
	if err != nil {
		return nil, errCert
	}
	digest := sha256.Sum256(contents)
	if hex.EncodeToString(digest[:]) != expectedHash {
		return nil, errCert
	}
	publicKey, err := kubeseal.ParseKey(bytes.NewReader(contents))
	if err != nil {
		return nil, errCert
	}
	return publicKey, nil
}

func (e strictEncryptor) Encrypt(data []byte) (string, error) {
	var output bytes.Buffer
	if err := kubeseal.EncryptSecretItem(&output, secretName, secretNamespace, data, ssv1alpha1.StrictScope, e.publicKey); err != nil {
		return "", errSeal
	}
	return strings.TrimSpace(output.String()), nil
}
