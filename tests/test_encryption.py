"""Task B tests: encrypted local file DBs (SQLCipher / DuckDB) and passphrase secrecy."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from dbvisual.core.connections import (
    ConnectionConfig,
    build_engine,
    encryption_supported,
)
from dbvisual.core.introspect import list_tables, reflect_schema
from dbvisual.meta.secrets import SecretStore
from dbvisual.meta.store import MetadataStore

pytest.importorskip("duckdb_engine")


# --- support detection & graceful degradation ------------------------------


def test_encryption_supported_flags() -> None:
    # DuckDB encryption ships with the duckdb_engine package.
    assert encryption_supported("duckdb") is True
    # SQLCipher needs a separate driver; typically absent in CI.
    assert isinstance(encryption_supported("sqlcipher"), bool)


def test_sqlcipher_without_driver_raises_clear_error() -> None:
    if encryption_supported("sqlcipher"):
        pytest.skip("SQLCipher driver installed; degradation path not exercised")
    with pytest.raises(RuntimeError, match="SQLCipher"):
        build_engine(
            ConnectionConfig(dialect="sqlcipher", database="x.db", encryption_key="k")
        )


# --- passphrase is a secret, never in the metadata store -------------------


def test_passphrase_not_in_metadata_store(tmp_path: Path) -> None:
    store = MetadataStore(tmp_path / "meta.db")
    secrets = SecretStore(use_keyring=False, data_dir=tmp_path)
    cid = store.create_connection(name="enc", dialect="duckdb", database="d.duckdb")
    secrets.set_secret(f"enckey:{cid}", "TopS3cretPass")

    assert secrets.get_secret(f"enckey:{cid}") == "TopS3cretPass"
    dump = (tmp_path / "meta.db").read_bytes()
    assert b"TopS3cretPass" not in dump
    vault = (tmp_path / "secrets.enc").read_bytes()
    assert b"TopS3cretPass" not in vault  # encrypted at rest


# --- encrypted DuckDB round-trip (real) ------------------------------------


def _make(path: str, key: str):
    return build_engine(
        ConnectionConfig(dialect="duckdb", database=path, encryption_key=key)
    )


def test_encrypted_duckdb_roundtrip(tmp_path: Path) -> None:
    db = str(tmp_path / "enc.duckdb")
    engine = _make(db, "correct-horse")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE secrets_tbl(a INTEGER, b VARCHAR)"))
        conn.execute(text("INSERT INTO secrets_tbl VALUES (1, 'hush')"))
    engine.dispose()

    # Reopen with the correct passphrase.
    engine_ok = _make(db, "correct-horse")
    metadata = reflect_schema(engine_ok)
    assert "secrets_tbl" in list_tables(metadata)
    with engine_ok.connect() as conn:
        assert conn.execute(text("SELECT b FROM secrets_tbl")).scalar_one() == "hush"
    engine_ok.dispose()


def test_encrypted_duckdb_wrong_passphrase(tmp_path: Path) -> None:
    db = str(tmp_path / "enc2.duckdb")
    engine = _make(db, "right-key")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t(a INTEGER)"))
    engine.dispose()

    engine_bad = _make(db, "wrong-key")
    with pytest.raises(Exception):
        reflect_schema(engine_bad)


def test_encrypted_duckdb_requires_path() -> None:
    with pytest.raises(ValueError):
        build_engine(
            ConnectionConfig(dialect="duckdb", database=":memory:", encryption_key="k")
        )


# --- SQLCipher round-trip (skipped when the driver is not installed) --------


@pytest.mark.skipif(
    not encryption_supported("sqlcipher"),
    reason="SQLCipher driver (pysqlcipher3/sqlcipher3) not installed",
)
def test_sqlcipher_roundtrip(tmp_path: Path) -> None:  # pragma: no cover - env dependent
    db = str(tmp_path / "enc.sqlcipher")
    engine = build_engine(
        ConnectionConfig(dialect="sqlcipher", database=db, encryption_key="pw123")
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t(a INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (1)"))
    engine.dispose()

    ok = build_engine(
        ConnectionConfig(dialect="sqlcipher", database=db, encryption_key="pw123")
    )
    with ok.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM t")).scalar_one() == 1
    ok.dispose()

    bad = build_engine(
        ConnectionConfig(dialect="sqlcipher", database=db, encryption_key="WRONG")
    )
    with pytest.raises(Exception):
        with bad.connect() as conn:
            conn.execute(text("SELECT count(*) FROM t")).scalar_one()
