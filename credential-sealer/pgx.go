package main

import (
	"context"

	"github.com/jackc/pgx/v5"
)

type pgxDatabase struct {
	conn    *pgx.Conn
	runtime string
}
type pgxTransaction struct{ tx pgx.Tx }

func connectDatabase(ctx context.Context, dbURL string) (*pgxDatabase, error) {
	connConfig, err := pgx.ParseConfig(dbURL)
	if err != nil {
		return nil, errDB
	}
	connConfig.RuntimeParams["default_transaction_read_only"] = "on"
	connConfig.RuntimeParams["statement_timeout"] = "15s"
	connConfig.RuntimeParams["lock_timeout"] = "2s"
	connConfig.RuntimeParams["idle_in_transaction_session_timeout"] = "20s"
	conn, err := pgx.ConnectConfig(ctx, connConfig)
	if err != nil {
		return nil, errDB
	}
	return &pgxDatabase{conn: conn, runtime: requiredRuntimeParams}, nil
}

func (d *pgxDatabase) RuntimeParams() string           { return d.runtime }
func (d *pgxDatabase) Close(ctx context.Context) error { return d.conn.Close(ctx) }
func (d *pgxDatabase) BeginReadOnlyRepeatableRead(ctx context.Context) (transaction, error) {
	tx, err := d.conn.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead, AccessMode: pgx.ReadOnly})
	if err != nil {
		return nil, err
	}
	return &pgxTransaction{tx: tx}, nil
}
func (t *pgxTransaction) QuerySettings(ctx context.Context) (string, string, error) {
	var readOnly, isolation string
	err := t.tx.QueryRow(ctx, "SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation')").Scan(&readOnly, &isolation)
	return readOnly, isolation, err
}
func (t *pgxTransaction) QueryCredentials(ctx context.Context, query string, accountID, siteID int64) ([]credentialRow, error) {
	rows, err := t.tx.Query(ctx, query, accountID, siteID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := make([]credentialRow, 0, 2)
	for rows.Next() {
		var row credentialRow
		if err := rows.Scan(&row.username, &row.passwordCipher); err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return result, nil
}
func (t *pgxTransaction) Rollback(ctx context.Context) error { return t.tx.Rollback(ctx) }
