package main

import (
	"context"
)

func run(ctx context.Context, cfg config) ([]byte, error) {
	defer clear(cfg.credentialSecret)
	db, err := connectDatabase(ctx, cfg.dbURL)
	if err != nil {
		return nil, errDB
	}
	row, loadErr := loadCredential(ctx, db, cfg.accountID, cfg.siteID)
	closeErr := db.Close(ctx)
	if loadErr != nil {
		return nil, loadErr
	}
	if closeErr != nil {
		return nil, errDB
	}
	password, err := decryptEnvelope(cfg.credentialSecret, row.passwordCipher)
	if err != nil {
		return nil, errDecrypt
	}
	defer clear(password)
	publicKey, err := loadCertificate(cfg.certPath)
	if err != nil {
		return nil, errCert
	}
	return buildOutput(strictEncryptor{publicKey: publicKey}, []byte(row.username), password)
}
