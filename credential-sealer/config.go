package main

import (
	"errors"
	"strconv"
	"strings"
)

const certificateSHA256 = "1b79ae46e6f8d45bef750b43b25183f8f0e3a2999c6acb9744acb2be9c9197ad"

type config struct {
	dbURL            string
	credentialSecret []byte
	accountID        int64
	siteID           int64
	certPath         string
}

func parseConfig(getenv func(string) string) (config, error) {
	dbURL := getenv("DB_URL")
	secret := strings.TrimSpace(getenv("ACCOUNT_CREDENTIAL_SECRET"))
	certPath := getenv("SEALED_SECRETS_CERT_PATH")
	if dbURL == "" || secret == "" || certPath == "" || getenv("SEALED_SECRETS_CERT_SHA256") != certificateSHA256 {
		return config{}, errInternal
	}
	accountID, err := parsePositiveID(getenv("AUTHORIZED_ACCOUNT_ID"))
	if err != nil {
		return config{}, errInternal
	}
	siteID, err := parsePositiveID(getenv("AUTHORIZED_SITE_ID"))
	if err != nil {
		return config{}, errInternal
	}
	return config{dbURL: dbURL, credentialSecret: []byte(secret), accountID: accountID, siteID: siteID, certPath: certPath}, nil
}

func parsePositiveID(value string) (int64, error) {
	if value == "" {
		return 0, errors.New("empty ID")
	}
	id, err := strconv.ParseInt(value, 10, 64)
	if err != nil || id <= 0 || strconv.FormatInt(id, 10) != value {
		return 0, errors.New("invalid ID")
	}
	return id, nil
}
