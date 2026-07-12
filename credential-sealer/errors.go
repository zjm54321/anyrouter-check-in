package main

import "errors"

var (
	errDB          = errors.New("database failure")
	errCardinality = errors.New("credential cardinality failure")
	errDecrypt     = errors.New("credential decryption failure")
	errCert        = errors.New("certificate failure")
	errSeal        = errors.New("sealing failure")
	errInternal    = errors.New("internal failure")
)

func failureCode(err error) string {
	switch {
	case errors.Is(err, errDB):
		return "FAIL_DB"
	case errors.Is(err, errCardinality):
		return "FAIL_CARDINALITY"
	case errors.Is(err, errDecrypt):
		return "FAIL_DECRYPT"
	case errors.Is(err, errCert):
		return "FAIL_CERT"
	case errors.Is(err, errSeal):
		return "FAIL_SEAL"
	default:
		return "FAIL_INTERNAL"
	}
}
