package main

import (
	"context"
	"os"
	"time"
)

func main() {
	_ = os.Setenv("GOTRACEBACK", "none")
	cfg, err := parseConfig(os.Getenv)
	if err != nil {
		writeFailure(err)
		os.Exit(1)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	output, err := run(ctx, cfg)
	if err != nil {
		writeFailure(err)
		os.Exit(1)
	}
	_, _ = os.Stdout.Write(output)
}

func writeFailure(err error) { _, _ = os.Stdout.WriteString(failureCode(err) + "\n") }
