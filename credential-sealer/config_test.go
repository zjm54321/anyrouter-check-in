package main

import "testing"

func TestParseConfigStrict(t *testing.T) {
	env := map[string]string{
		"DB_URL": "postgres://db/proof", "ACCOUNT_CREDENTIAL_SECRET": "dedicated",
		"AUTHORIZED_ACCOUNT_ID": "7", "AUTHORIZED_SITE_ID": "9",
		"SEALED_SECRETS_CERT_PATH": "/cert/tls.crt", "SEALED_SECRETS_CERT_SHA256": certificateSHA256,
	}
	cfg, err := parseConfig(func(key string) string { return env[key] })
	if err != nil || cfg.accountID != 7 || cfg.siteID != 9 {
		t.Fatalf("parseConfig() = %#v, %v", cfg, err)
	}
	for _, key := range []string{"DB_URL", "ACCOUNT_CREDENTIAL_SECRET", "SEALED_SECRETS_CERT_PATH"} {
		copy := mapsClone(env)
		delete(copy, key)
		if _, err := parseConfig(func(k string) string { return copy[k] }); err == nil {
			t.Errorf("missing %s accepted", key)
		}
	}
	for _, value := range []string{"", "0", "-1", "x", " 7"} {
		copy := mapsClone(env)
		copy["AUTHORIZED_ACCOUNT_ID"] = value
		if _, err := parseConfig(func(k string) string { return copy[k] }); err == nil {
			t.Errorf("account ID %q accepted", value)
		}
	}
	copy := mapsClone(env)
	copy["SEALED_SECRETS_CERT_SHA256"] = "1b79AE46e6f8d45bef750b43b25183f8f0e3a2999c6acb9744acb2be9c9197ad"
	if _, err := parseConfig(func(k string) string { return copy[k] }); err == nil {
		t.Fatal("non-exact cert hash accepted")
	}
}

func TestParseConfigTrimsCredentialSecretOnly(t *testing.T) {
	env := map[string]string{
		"DB_URL": " postgres://db/proof ", "ACCOUNT_CREDENTIAL_SECRET": " \t dedicated-secret \r\n",
		"AUTHORIZED_ACCOUNT_ID": "7", "AUTHORIZED_SITE_ID": "9",
		"SEALED_SECRETS_CERT_PATH": "/cert/tls.crt", "SEALED_SECRETS_CERT_SHA256": certificateSHA256,
	}
	cfg, err := parseConfig(func(key string) string { return env[key] })
	if err != nil {
		t.Fatal(err)
	}
	if string(cfg.credentialSecret) != "dedicated-secret" {
		t.Fatalf("credential secret = %q", cfg.credentialSecret)
	}
	if cfg.dbURL != env["DB_URL"] {
		t.Fatalf("DB URL was trimmed: %q", cfg.dbURL)
	}
	env["ACCOUNT_CREDENTIAL_SECRET"] = " \t\r\n "
	if _, err := parseConfig(func(key string) string { return env[key] }); err == nil {
		t.Fatal("all-whitespace secret accepted")
	}
}

func mapsClone(source map[string]string) map[string]string {
	result := make(map[string]string, len(source))
	for k, v := range source {
		result[k] = v
	}
	return result
}
