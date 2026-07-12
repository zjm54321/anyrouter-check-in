package main

import (
	"errors"
	"strings"
	"testing"
)

type fakeEncryptor struct {
	calls  []string
	failAt int
}

func (f *fakeEncryptor) Encrypt(data []byte) (string, error) {
	f.calls = append(f.calls, string(data))
	if len(f.calls) == f.failAt {
		return "", errors.New("private raw")
	}
	return "Ag" + strings.Repeat("x", len(f.calls)), nil
}

func TestBuildOutputStrictSchemaAndScope(t *testing.T) {
	f := &fakeEncryptor{}
	out, err := buildOutput(f, []byte("user@example.test"), []byte("pw"))
	if err != nil {
		t.Fatal(err)
	}
	want := "apiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n  name: anyrouter-check-in-once\n  namespace: ai-services\nspec:\n  encryptedData:\n    email: Agx\n    password: Agxx\n  template:\n    metadata:\n      name: anyrouter-check-in-once\n      namespace: ai-services\n    type: Opaque\n    immutable: true\n# status: SEALED_OK\n"
	if string(out) != want {
		t.Fatalf("output:\n%s", out)
	}
	for _, forbidden := range []string{"stringData:", "\n  data:", "source", "user@example.test", "pw"} {
		if strings.Contains(string(out), forbidden) {
			t.Errorf("contains %q", forbidden)
		}
	}
}

func TestBuildOutputNoPartialOnSecondEncryptionFailure(t *testing.T) {
	f := &fakeEncryptor{failAt: 2}
	out, err := buildOutput(f, []byte("email"), []byte("password"))
	if !errors.Is(err, errSeal) || out != nil {
		t.Fatalf("out=%q err=%v", out, err)
	}
}

func TestFailureCodesAreFixed(t *testing.T) {
	for input, want := range map[error]string{errDB: "FAIL_DB", errCardinality: "FAIL_CARDINALITY", errDecrypt: "FAIL_DECRYPT", errCert: "FAIL_CERT", errSeal: "FAIL_SEAL", errInternal: "FAIL_INTERNAL", errors.New("raw password SQL stack"): "FAIL_INTERNAL"} {
		if got := failureCode(input); got != want || strings.Contains(got, "raw") {
			t.Errorf("got %q want %q", got, want)
		}
	}
}
