package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStaticSecurityPolicy(t *testing.T) {
	entries, err := filepath.Glob("*.go")
	if err != nil {
		t.Fatal(err)
	}
	for _, path := range entries {
		if strings.HasSuffix(path, "_test.go") {
			continue
		}
		contents, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		text := string(contents)
		for _, forbidden := range []string{"os/exec", "exec.Command", "kubeseal CLI", "AUTH_TOKEN", "envFrom", "checksum bypass"} {
			if strings.Contains(text, forbidden) {
				t.Errorf("%s contains forbidden %q", path, forbidden)
			}
		}
	}
	dockerfile, err := os.ReadFile("Dockerfile")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(dockerfile), "/bin/sh") || strings.Contains(string(dockerfile), "ENTRYPOINT [\"sh\"") {
		t.Fatal("runtime uses shell")
	}
	workflow, err := os.ReadFile(filepath.Join("..", ".github", "workflows", "credential-sealer-image.yml"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(workflow)
	for _, forbidden := range []string{"pull_request:", "push:\n", ":latest", "envFrom", "--password ", "--secret "} {
		if strings.Contains(text, forbidden) {
			t.Errorf("workflow contains %q", forbidden)
		}
	}
	for _, required := range []string{"workflow_dispatch:", "go test -race -shuffle=on -count=1 ./...", "go vet ./...", "CGO_ENABLED: '0'", "linux/amd64", "${GITHUB_SHA}", "digest="} {
		if !strings.Contains(text, required) {
			t.Errorf("workflow missing %q", required)
		}
	}
}
