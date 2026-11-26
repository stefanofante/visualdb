"""Encrypted credential handling for saved connections.

Passwords are never stored in the metadata database. The primary backend is the
OS keyring (via ``keyring``); when no usable keyring backend is available the
code falls back to a local file encrypted with ``cryptography.Fernet``. The
Fernet key is generated once and stored in the user data directory with
restrictive permissions.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet
from filelock import FileLock
from platformdirs import user_data_dir

from dbvisual.meta.local_files import atomic_write

_APP_NAME = "dbvisual"
_KEYRING_SERVICE = "dbvisual"


def _data_dir() -> Path:
    """Return the user data directory, creating it if necessary."""
    path = Path(user_data_dir(_APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


class SecretStore:
    """Store/retrieve connection passwords via keyring or an encrypted fallback.

    Set ``use_keyring=False`` (as tests do) to force the local Fernet fallback
    without touching the real OS keyring.
    """

    def __init__(
        self,
        use_keyring: bool = True,
        data_dir: str | Path | None = None,
    ) -> None:
        self._use_keyring = use_keyring
        self._dir = Path(data_dir) if data_dir is not None else _data_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(self._dir / "vault.lock", timeout=10)
        self._key_path = self._dir / "secret.key"
        self._vault_path = self._dir / "secrets.enc"

    # -- public API ---------------------------------------------------------

    def save_password(self, connection_id: int, password: str) -> None:
        """Persist ``password`` for ``connection_id``."""
        self.set_secret(str(connection_id), password)

    def get_password(self, connection_id: int) -> str | None:
        """Return the stored password for ``connection_id`` or ``None``."""
        return self.get_secret(str(connection_id))

    def delete_password(self, connection_id: int) -> None:
        """Remove any stored password for ``connection_id`` (no-op if absent)."""
        self.delete_secret(str(connection_id))

    # -- generic secrets (passwords, webhook URLs, ...) ---------------------

    def set_secret(self, key: str, value: str) -> None:
        """Persist an arbitrary secret ``value`` under ``key``."""
        if self._keyring_available():
            import keyring

            keyring.set_password(_KEYRING_SERVICE, key, value)
            return
        with self._lock:
            vault = self._load_vault()
            vault[key] = value
            self._write_vault(vault)

    def get_secret(self, key: str) -> str | None:
        """Return the secret stored under ``key`` or ``None``."""
        if self._keyring_available():
            import keyring

            return keyring.get_password(_KEYRING_SERVICE, key)
        with self._lock:
            return self._load_vault().get(key)

    def delete_secret(self, key: str) -> None:
        """Remove the secret under ``key`` (no-op if absent)."""
        if self._keyring_available():
            import keyring
            import keyring.errors

            try:
                keyring.delete_password(_KEYRING_SERVICE, key)
            except keyring.errors.PasswordDeleteError:
                pass
            return
        with self._lock:
            vault = self._load_vault()
            if key in vault:
                del vault[key]
                self._write_vault(vault)

    # -- keyring detection --------------------------------------------------

    def _keyring_available(self) -> bool:
        """Return ``True`` when a real (non-fail) keyring backend is usable."""
        if not self._use_keyring:
            return False
        try:
            import keyring
            from keyring.backends.fail import Keyring as FailKeyring

            backend = keyring.get_keyring()
            return not isinstance(backend, FailKeyring)
        except Exception:
            return False

    # -- Fernet fallback ----------------------------------------------------

    def _load_key(self) -> bytes:
        """Load or lazily create the Fernet key with restrictive permissions."""
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = Fernet.generate_key()
        atomic_write(self._key_path, key)
        return key

    def _fernet(self) -> Fernet:
        return Fernet(self._load_key())

    def _load_vault(self) -> dict[str, str]:
        """Decrypt and return the fallback vault as a dict."""
        if not self._vault_path.exists():
            return {}
        token = self._vault_path.read_bytes()
        if not token or not self._key_path.exists():
            raise ValueError("The encrypted vault or its key is incomplete.")
        data = self._fernet().decrypt(token)
        return json.loads(data.decode("utf-8"))

    def _write_vault(self, vault: dict[str, str]) -> None:
        """Encrypt and persist the fallback vault with restrictive permissions."""
        token = self._fernet().encrypt(json.dumps(vault).encode("utf-8"))
        atomic_write(self._vault_path, token)
