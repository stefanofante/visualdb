"""Tests for the secret store using the encrypted Fernet fallback.

The real OS keyring is never touched: ``use_keyring=False`` forces the local
encrypted-file backend into a temporary directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dbvisual.meta.secrets import SecretStore


@pytest.fixture()
def secrets(tmp_path: Path) -> SecretStore:
    return SecretStore(use_keyring=False, data_dir=tmp_path)


def test_password_roundtrip(secrets: SecretStore) -> None:
    secrets.save_password(1, "s3cr3t")
    assert secrets.get_password(1) == "s3cr3t"


def test_missing_password_returns_none(secrets: SecretStore) -> None:
    assert secrets.get_password(999) is None


def test_overwrite_password(secrets: SecretStore) -> None:
    secrets.save_password(2, "first")
    secrets.save_password(2, "second")
    assert secrets.get_password(2) == "second"


def test_delete_password(secrets: SecretStore) -> None:
    secrets.save_password(3, "todelete")
    secrets.delete_password(3)
    assert secrets.get_password(3) is None
    # Deleting again is a no-op.
    secrets.delete_password(3)


def test_vault_is_encrypted_on_disk(tmp_path: Path) -> None:
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    secrets.save_password(4, "plaintext-value")
    vault = tmp_path / "secrets.enc"
    assert vault.exists()
    raw = vault.read_bytes()
    # The plaintext must not be recoverable from the encrypted file.
    assert b"plaintext-value" not in raw


def test_persistence_across_instances(tmp_path: Path) -> None:
    SecretStore(use_keyring=False, data_dir=tmp_path).save_password(5, "persisted")
    reopened = SecretStore(use_keyring=False, data_dir=tmp_path)
    assert reopened.get_password(5) == "persisted"
