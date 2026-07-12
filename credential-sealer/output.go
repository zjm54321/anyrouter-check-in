package main

import (
	"fmt"
)

const secretName = "anyrouter-check-in-once"
const secretNamespace = "ai-services"

type itemEncryptor interface{ Encrypt([]byte) (string, error) }

func buildOutput(encryptor itemEncryptor, email, password []byte) ([]byte, error) {
	sealedEmail, err := encryptor.Encrypt(email)
	if err != nil {
		return nil, errSeal
	}
	sealedPassword, err := encryptor.Encrypt(password)
	if err != nil {
		return nil, errSeal
	}
	result := fmt.Sprintf("apiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n  name: %s\n  namespace: %s\nspec:\n  encryptedData:\n    email: %s\n    password: %s\n  template:\n    metadata:\n      name: %s\n      namespace: %s\n    type: Opaque\n    immutable: true\n# status: SEALED_OK\n", secretName, secretNamespace, sealedEmail, sealedPassword, secretName, secretNamespace)
	return []byte(result), nil
}
