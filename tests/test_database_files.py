from concurrent.futures import ThreadPoolExecutor

import pytest

from dbvisual.app.database_files import create_database_file
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import list_tables, reflect_schema


@pytest.mark.parametrize("dialect", ["sqlite", "duckdb"])
def test_new_file_reopens_without_tables_and_is_never_overwritten(tmp_path, dialect):
    def create():
        try:
            return create_database_file(dialect, str(tmp_path), "My practice data")
        except FileExistsError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    path = tmp_path / f"My practice data.{dialect}"
    assert set(results) == {path, None}
    assert path.stat().st_size > 0
    engine = build_engine(ConnectionConfig(dialect=dialect, database=str(path)))
    try:
        assert list_tables(reflect_schema(engine)) == []
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE example (id INTEGER)")
    finally:
        engine.dispose()
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        create_database_file(dialect, str(tmp_path), path.name)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_file_creation_failure_leaves_no_database(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("read-only volume")

    monkeypatch.setattr("dbvisual.app.database_files.os.replace", fail)
    with pytest.raises(OSError, match="read-only volume"):
        create_database_file("sqlite", str(tmp_path), "practice")
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError, match="file name"):
        create_database_file("duckdb", str(tmp_path), "../practice")
