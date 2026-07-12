package main

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

type fakeTx struct {
	calls         []string
	args          []any
	rows          []credentialRow
	queryErr      error
	rollbackCount int
}

func (f *fakeTx) QuerySettings(context.Context) (string, string, error) {
	f.calls = append(f.calls, "settings")
	return "on", "repeatable read", nil
}
func (f *fakeTx) QueryCredentials(_ context.Context, sql string, accountID, siteID int64) ([]credentialRow, error) {
	f.calls = append(f.calls, sql)
	f.args = []any{accountID, siteID}
	return f.rows, f.queryErr
}
func (f *fakeTx) Rollback(context.Context) error {
	f.calls = append(f.calls, "rollback")
	f.rollbackCount++
	return nil
}

type fakeDB struct {
	runtime string
	tx      *fakeTx
	began   bool
}

func (f *fakeDB) RuntimeParams() string { return f.runtime }
func (f *fakeDB) BeginReadOnlyRepeatableRead(context.Context) (transaction, error) {
	f.began = true
	return f.tx, nil
}

func TestLoadCredentialExactQueryAndRollback(t *testing.T) {
	tx := &fakeTx{rows: []credentialRow{{username: "a@b", passwordCipher: "cipher"}}}
	db := &fakeDB{runtime: requiredRuntimeParams, tx: tx}
	row, err := loadCredential(context.Background(), db, 41, 53)
	if err != nil || row.username != "a@b" || tx.rollbackCount != 1 {
		t.Fatalf("load = %#v %v rollbacks=%d", row, err, tx.rollbackCount)
	}
	if !reflect.DeepEqual(tx.args, []any{int64(41), int64(53)}) {
		t.Fatalf("args = %#v", tx.args)
	}
	if len(tx.calls) != 3 || tx.calls[0] != "settings" || tx.calls[2] != "rollback" {
		t.Fatalf("calls = %#v", tx.calls)
	}
	for _, required := range []string{"accounts.extra_config", "accounts.site_id = sites.id", "sites.platform = 'anyrouter'", "credentialMode", "jsonb_typeof(accounts.extra_config->'autoRelogin') = 'object'", "NULLIF(BTRIM(accounts.extra_config->'autoRelogin'->>'username'), '') IS NOT NULL", "NULLIF(BTRIM(accounts.extra_config->'autoRelogin'->>'passwordCipher'), '') IS NOT NULL", "accounts.status = 'active'", "sites.status = 'active'", "checkin_enabled = true", "$1", "$2", "LIMIT 2"} {
		if !contains(tx.calls[1], required) {
			t.Errorf("query missing %q", required)
		}
	}
}

func TestLoadCredentialCardinalityAndQueryFailure(t *testing.T) {
	for _, rows := range [][]credentialRow{nil, {{}, {}}} {
		tx := &fakeTx{rows: rows}
		_, err := loadCredential(context.Background(), &fakeDB{runtime: requiredRuntimeParams, tx: tx}, 1, 2)
		if !errors.Is(err, errCardinality) || tx.rollbackCount != 1 {
			t.Fatalf("rows=%d err=%v rollbacks=%d", len(rows), err, tx.rollbackCount)
		}
	}
	tx := &fakeTx{queryErr: errors.New("raw SQL error")}
	_, err := loadCredential(context.Background(), &fakeDB{runtime: requiredRuntimeParams, tx: tx}, 1, 2)
	if !errors.Is(err, errDB) || tx.rollbackCount != 1 {
		t.Fatalf("err=%v rollbacks=%d", err, tx.rollbackCount)
	}
}

func TestLoadCredentialNormalizesAndRejectsBlankFields(t *testing.T) {
	tx := &fakeTx{rows: []credentialRow{{username: " \tuser@example.test\r\n", passwordCipher: "v1:a:b:c"}}}
	row, err := loadCredential(context.Background(), &fakeDB{runtime: requiredRuntimeParams, tx: tx}, 1, 2)
	if err != nil || row.username != "user@example.test" {
		t.Fatalf("row=%#v err=%v", row, err)
	}
	for _, row := range []credentialRow{{username: " \t", passwordCipher: "cipher"}, {username: "user", passwordCipher: "\r\n "}} {
		tx := &fakeTx{rows: []credentialRow{row}}
		_, err := loadCredential(context.Background(), &fakeDB{runtime: requiredRuntimeParams, tx: tx}, 1, 2)
		if !errors.Is(err, errCardinality) || tx.rollbackCount != 1 {
			t.Fatalf("row=%#v err=%v rollbacks=%d", row, err, tx.rollbackCount)
		}
	}
}

func contains(value, part string) bool {
	for i := 0; i+len(part) <= len(value); i++ {
		if value[i:i+len(part)] == part {
			return true
		}
	}
	return false
}
