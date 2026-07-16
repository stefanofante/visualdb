"""Tests for Phase 6: master-detail atomic save (one-to-many & many-to-many)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import (
    Column as SACol,
)
from sqlalchemy import (
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.pool import StaticPool

from dbvisual.app.master_detail_service import (
    ConflictError,
    DetailChange,
    DetailQuery,
    MasterDetailSpec,
    build_save_plan,
    execute_save,
    load_details,
    suggest_detail_fk,
    validate_detail_query,
)
from dbvisual.app.sheet_service import build_view, get_table
from dbvisual.core.connections import ConnectionConfig, build_engine
from dbvisual.core.introspect import reflect_schema
from dbvisual.core.queryspec import Column, Filter, Param, QuerySpec, Related

# --- specs -----------------------------------------------------------------


def _master_spec() -> QuerySpec:
    return QuerySpec(
        main_table="customers",
        columns=[
            Column(table="customers", name="id", alias="id"),
            Column(table="customers", name="name", alias="name"),
            Column(table="customers", name="city", alias="city"),
        ],
    )


def _orders_detail() -> DetailQuery:
    spec = QuerySpec(
        main_table="orders",
        columns=[
            Column(table="orders", name="id", alias="id"),
            Column(table="orders", name="customer_id", alias="customer_id"),
            Column(table="orders", name="amount", alias="amount"),
        ],
        filters=[
            Filter(
                column=Column(table="orders", name="customer_id"),
                op="eq",
                param="master",
            )
        ],
        params=[Param(name="master", type="integer")],
    )
    return DetailQuery(spec=spec, param_name="master", fk_column="customer_id")


# --- validation & FK detection ---------------------------------------------


def test_roundtrip(tmp_path: Path) -> None:
    from dbvisual.meta.store import MetadataStore

    store = MetadataStore(tmp_path / "m.db")
    app_id = store.create_application("A")
    md = MasterDetailSpec(
        connection_id=1, master_spec=_master_spec(), details=[_orders_detail()]
    )
    did = store.create_definition(app_id, "master_detail", "MD", md.to_json())
    got = store.get_definition(did)
    assert got is not None and got["kind"] == "master_detail"
    assert len(MasterDetailSpec.from_json(got["queryspec_json"]).details) == 1


def test_detail_must_have_exactly_one_param() -> None:
    ok = _orders_detail()
    validate_detail_query(ok)  # one param -> fine

    zero = _orders_detail()
    zero.spec.params = []
    with pytest.raises(ValueError):
        validate_detail_query(zero)

    two = _orders_detail()
    two.spec.params.append(Param(name="extra"))
    with pytest.raises(ValueError):
        validate_detail_query(two)


def test_suggest_detail_fk(metadata: MetaData) -> None:
    assert suggest_detail_fk(metadata, "customers", "orders") == ("customer_id", "id")
    assert suggest_detail_fk(metadata, "orders", "customers") is None


def test_load_details_only_linked(engine: Engine, metadata: MetaData) -> None:
    _f, rows = load_details(engine, metadata, _orders_detail(), 1)
    assert {r["id"] for r in rows} == {10, 11}  # customer 1's orders only


# --- atomic one-to-many ----------------------------------------------------


def test_atomic_save_one_to_many(engine: Engine, metadata: MetaData) -> None:
    mview = build_view(_master_spec(), metadata)
    mtable = get_table(metadata, "customers")
    detail = _orders_detail()
    dview = build_view(detail.spec, metadata)
    dtable = get_table(metadata, "orders")

    changes = DetailChange(
        view=dview,
        table=dtable,
        fk_column="customer_id",
        updates=[{"id": 10, "customer_id": 1, "amount": 999}],
        deletes=[{"id": 11, "customer_id": 1, "amount": 250}],
        inserts=[{"amount": 42}],
    )
    plan = build_save_plan(
        master_view=mview,
        master_table=mtable,
        master_record={"id": 1, "name": "Alice", "city": "Napoli"},
        master_is_new=False,
        master_original={"id": 1, "name": "Alice", "city": "Rome"},
        details=[changes],
        master_pk_value=1,
    )
    execute_save(engine, plan)

    with engine.connect() as conn:
        city = conn.execute(select(mtable.c.city).where(mtable.c.id == 1)).scalar_one()
        orders = {
            r.id: r.amount
            for r in conn.execute(
                select(dtable.c.id, dtable.c.amount).where(dtable.c.customer_id == 1)
            )
        }
    assert city == "Napoli"  # master updated
    assert orders[10] == 999  # detail updated
    assert 11 not in orders  # detail deleted
    assert any(a == 42 for a in orders.values())  # detail inserted with fk=1


def test_detail_error_rolls_back_master(engine: Engine, metadata: MetaData) -> None:
    mview = build_view(_master_spec(), metadata)
    mtable = get_table(metadata, "customers")
    detail = _orders_detail()
    dview = build_view(detail.spec, metadata)
    dtable = get_table(metadata, "orders")

    # Insert a detail without 'amount' (NOT NULL) -> integrity error.
    changes = DetailChange(
        view=dview, table=dtable, fk_column="customer_id", inserts=[{}]
    )
    plan = build_save_plan(
        master_view=mview,
        master_table=mtable,
        master_record={"id": 1, "name": "Alice", "city": "SHOULD_ROLLBACK"},
        master_is_new=False,
        master_original={"id": 1, "name": "Alice", "city": "Rome"},
        details=[changes],
        master_pk_value=1,
    )
    with pytest.raises(Exception):
        execute_save(engine, plan)

    with engine.connect() as conn:
        city = conn.execute(select(mtable.c.city).where(mtable.c.id == 1)).scalar_one()
    assert city == "Rome"  # master change rolled back too


def test_new_master_pk_propagated_to_details(
    engine: Engine, metadata: MetaData
) -> None:
    mview = build_view(_master_spec(), metadata)
    mtable = get_table(metadata, "customers")
    detail = _orders_detail()
    dview = build_view(detail.spec, metadata)
    dtable = get_table(metadata, "orders")

    changes = DetailChange(
        view=dview,
        table=dtable,
        fk_column="customer_id",
        inserts=[{"amount": 500}],
    )
    plan = build_save_plan(
        master_view=mview,
        master_table=mtable,
        master_record={"name": "Dora", "city": "Bari"},
        master_is_new=True,
        master_original=None,
        details=[changes],
        master_pk_value=None,
    )
    execute_save(engine, plan)

    with engine.connect() as conn:
        new_id = conn.execute(
            select(mtable.c.id).where(mtable.c.name == "Dora")
        ).scalar_one()
        fk = conn.execute(
            select(dtable.c.customer_id).where(dtable.c.amount == 500)
        ).scalar_one()
    assert fk == new_id  # detail FK got the generated master PK


def test_optimistic_locking_conflict_rolls_back(
    engine: Engine, metadata: MetaData
) -> None:
    mview = build_view(_master_spec(), metadata)
    mtable = get_table(metadata, "customers")
    detail = _orders_detail()
    dview = build_view(detail.spec, metadata)
    dtable = get_table(metadata, "orders")

    # Concurrent change to the master after "load".
    with engine.begin() as conn:
        conn.execute(mtable.update().where(mtable.c.id == 1).values(city="Concurrent"))

    changes = DetailChange(
        view=dview,
        table=dtable,
        fk_column="customer_id",
        inserts=[{"amount": 7}],
    )
    plan = build_save_plan(
        master_view=mview,
        master_table=mtable,
        master_record={"id": 1, "name": "Alice", "city": "Mine"},
        master_is_new=False,
        master_original={"id": 1, "name": "Alice", "city": "Rome"},  # stale
        details=[changes],
        master_pk_value=1,
    )
    with pytest.raises(ConflictError):
        execute_save(engine, plan)

    with engine.connect() as conn:
        city = conn.execute(select(mtable.c.city).where(mtable.c.id == 1)).scalar_one()
        n_new = conn.execute(select(dtable.c.id).where(dtable.c.amount == 7)).all()
    assert city == "Concurrent"  # our master write rolled back
    assert n_new == []  # detail insert rolled back


# --- many-to-many ----------------------------------------------------------


@pytest.fixture()
def m2m() -> tuple[Engine, MetaData]:
    """students / courses / student_course junction schema (in-memory)."""
    eng = build_engine(
        ConnectionConfig(
            dialect="sqlite",
            database=":memory:",
            engine_kwargs={
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            },
        )
    )
    meta = MetaData()
    students = Table(
        "students",
        meta,
        SACol("id", Integer, primary_key=True),
        SACol("name", String(50)),
    )
    courses = Table(
        "courses",
        meta,
        SACol("id", Integer, primary_key=True),
        SACol("title", String(50)),
    )
    Table(
        "student_course",
        meta,
        SACol("id", Integer, primary_key=True),
        SACol("student_id", Integer, ForeignKey("students.id"), nullable=False),
        SACol("course_id", Integer, ForeignKey("courses.id"), nullable=False),
    )
    meta.create_all(eng)
    with eng.begin() as conn:
        conn.execute(insert(students), [{"id": 1, "name": "Sam"}])
        conn.execute(
            insert(courses),
            [{"id": 100, "title": "Math"}, {"id": 200, "title": "Physics"}],
        )
    return eng, reflect_schema(eng)


def test_many_to_many_association(m2m: tuple[Engine, MetaData]) -> None:
    engine, metadata = m2m
    # Detail main table = junction; related = courses (read-only label).
    detail_spec = QuerySpec(
        main_table="student_course",
        columns=[
            Column(table="student_course", name="id", alias="id"),
            Column(table="student_course", name="student_id", alias="student_id"),
            Column(table="student_course", name="course_id", alias="course_id"),
            Column(table="courses", name="title", alias="course_title"),
        ],
        related=[Related(table="courses", local_col="course_id", remote_col="id")],
        filters=[
            Filter(
                column=Column(table="student_course", name="student_id"),
                op="eq",
                param="master",
            )
        ],
        params=[Param(name="master", type="integer")],
    )
    detail = DetailQuery(spec=detail_spec, param_name="master", fk_column="student_id")
    dview = build_view(detail_spec, metadata)
    dtable = get_table(metadata, "student_course")

    changes = DetailChange(
        view=dview,
        table=dtable,
        fk_column="student_id",
        # Associate student 1 with course 200; the related title must not be written.
        inserts=[{"course_id": 200, "course_title": "IGNORED"}],
    )
    plan = build_save_plan(
        master_view=build_view(
            QuerySpec(
                main_table="students",
                columns=[
                    Column(table="students", name="id", alias="id"),
                    Column(table="students", name="name", alias="name"),
                ],
            ),
            metadata,
        ),
        master_table=get_table(metadata, "students"),
        master_record={"id": 1, "name": "Sam"},
        master_is_new=False,
        master_original={"id": 1, "name": "Sam"},
        details=[changes],
        master_pk_value=1,
    )
    execute_save(engine, plan)

    with engine.connect() as conn:
        rows = conn.execute(select(dtable.c.student_id, dtable.c.course_id)).all()
        titles = {
            r.title
            for r in conn.execute(select(get_table(metadata, "courses").c.title))
        }
    assert (1, 200) in [(r.student_id, r.course_id) for r in rows]
    assert titles == {"Math", "Physics"}  # courses table untouched


# --- smoke -----------------------------------------------------------------


def test_master_detail_routes_registered() -> None:
    from nicegui import Client

    import dbvisual.app.main  # noqa: F401

    routes = set(Client.page_routes.values())
    assert "/master-detail" in routes
    assert "/master-detail/{definition_id}" in routes
