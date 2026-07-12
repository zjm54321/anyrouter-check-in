package main

import (
	"context"
	"errors"
	"strings"
)

const requiredRuntimeParams = "default_transaction_read_only=on statement_timeout=15s lock_timeout=2s idle_in_transaction_session_timeout=20s"

const credentialQuery = `SELECT accounts.extra_config->'autoRelogin'->>'username',
       accounts.extra_config->'autoRelogin'->>'passwordCipher'
FROM accounts JOIN sites ON accounts.site_id = sites.id
WHERE accounts.id = $1 AND sites.id = $2
  AND sites.platform = 'anyrouter'
  AND accounts.status = 'active' AND sites.status = 'active'
  AND accounts.checkin_enabled = true
  AND accounts.extra_config->>'credentialMode' = 'session'
  AND jsonb_typeof(accounts.extra_config->'autoRelogin') = 'object'
  AND NULLIF(BTRIM(accounts.extra_config->'autoRelogin'->>'username'), '') IS NOT NULL
  AND NULLIF(BTRIM(accounts.extra_config->'autoRelogin'->>'passwordCipher'), '') IS NOT NULL
LIMIT 2`

type credentialRow struct{ username, passwordCipher string }
type transaction interface {
	QuerySettings(context.Context) (string, string, error)
	QueryCredentials(context.Context, string, int64, int64) ([]credentialRow, error)
	Rollback(context.Context) error
}
type database interface {
	RuntimeParams() string
	BeginReadOnlyRepeatableRead(context.Context) (transaction, error)
}

func loadCredential(ctx context.Context, db database, accountID, siteID int64) (credentialRow, error) {
	if db.RuntimeParams() != requiredRuntimeParams {
		return credentialRow{}, errDB
	}
	tx, err := db.BeginReadOnlyRepeatableRead(ctx)
	if err != nil {
		return credentialRow{}, errDB
	}
	rolledBack := false
	rollback := func() error {
		if rolledBack {
			return nil
		}
		rolledBack = true
		return tx.Rollback(ctx)
	}
	readOnly, isolation, err := tx.QuerySettings(ctx)
	if err != nil || readOnly != "on" || isolation != "repeatable read" {
		_ = rollback()
		return credentialRow{}, errDB
	}
	rows, err := tx.QueryCredentials(ctx, credentialQuery, accountID, siteID)
	if err != nil {
		_ = rollback()
		return credentialRow{}, errDB
	}
	if len(rows) != 1 {
		_ = rollback()
		return credentialRow{}, errCardinality
	}
	rows[0].username = strings.TrimSpace(rows[0].username)
	if rows[0].username == "" || strings.TrimSpace(rows[0].passwordCipher) == "" {
		_ = rollback()
		return credentialRow{}, errCardinality
	}
	if err := rollback(); err != nil {
		return credentialRow{}, errors.Join(errDB, err)
	}
	return rows[0], nil
}
