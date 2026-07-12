package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/pem"
	"math/big"
	"os"
	"testing"
	"time"

	ssv1alpha1 "github.com/bitnami-labs/sealed-secrets/pkg/apis/sealedsecrets/v1alpha1"
	sscrypto "github.com/bitnami-labs/sealed-secrets/pkg/crypto"
)

func TestStrictEncryptorUsesStrictNameNamespaceLabel(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	ciphertextText, err := (strictEncryptor{publicKey: &privateKey.PublicKey}).Encrypt([]byte("secret-value"))
	if err != nil {
		t.Fatal(err)
	}
	ciphertext, err := base64.StdEncoding.DecodeString(ciphertextText)
	if err != nil {
		t.Fatal(err)
	}
	keys := map[string]*rsa.PrivateKey{"test": privateKey}
	label := ssv1alpha1.EncryptionLabel(secretNamespace, secretName, ssv1alpha1.StrictScope)
	plaintext, err := sscrypto.HybridDecrypt(rand.Reader, keys, ciphertext, label)
	if err != nil || string(plaintext) != "secret-value" {
		t.Fatalf("decrypt=%q err=%v", plaintext, err)
	}
	for _, wrong := range [][]byte{ssv1alpha1.EncryptionLabel(secretNamespace, "other", ssv1alpha1.StrictScope), ssv1alpha1.EncryptionLabel("other", secretName, ssv1alpha1.StrictScope)} {
		if _, err := sscrypto.HybridDecrypt(rand.Reader, keys, ciphertext, wrong); err == nil {
			t.Fatal("ciphertext decrypted with wrong strict-scope label")
		}
	}
}

func TestLoadCertificateWithExpectedHash(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	template := x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageKeyEncipherment}
	der, err := x509.CreateCertificate(rand.Reader, &template, &template, &privateKey.PublicKey, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	certificate := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	path := t.TempDir() + "/tls.crt"
	if err := os.WriteFile(path, certificate, 0o600); err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(certificate)
	expected := hex.EncodeToString(digest[:])
	publicKey, err := loadCertificateWithHash(path, expected)
	if err != nil || publicKey.N.Cmp(privateKey.N) != 0 {
		t.Fatalf("key=%v err=%v", publicKey, err)
	}
	if _, err := loadCertificateWithHash(path, certificateSHA256); err == nil {
		t.Fatal("incorrect production pin accepted")
	}
}
