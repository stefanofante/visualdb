"""Shared query-builder helpers (Phase 3+), reused by Sheets and Forms.

Implements the *many → one* join rule: the main table sits on the "many" side and
related tables are joined only by following their foreign key toward the "one"
side, guaranteeing one result row per main-table record. Only the main table is
updatable; related columns are added read-only.
"""

from __future__ import annotations

from sqlalchemy import MetaData

from dbvisual.core.introspect import (
    detect_foreign_keys,
    get_columns,
    get_primary_key,
    resolve_table,
)
from dbvisual.core.queryspec import Column, QuerySpec, Related


def related_candidates(metadata: MetaData, main_table: str) -> list[str]:
    """Return tables joinable *many → one* from ``main_table`` (FK toward "one")."""
    return [fk.remote_table for fk in detect_foreign_keys(metadata, main_table)]


def validate_related(metadata: MetaData, main_table: str, related_table: str) -> bool:
    """True if ``related_table`` is on the "one" side of an FK from ``main_table``."""
    return related_table in set(related_candidates(metadata, main_table))


def build_queryspec(
    metadata: MetaData,
    main_table: str,
    main_cols: list[str],
    related_tables: list[str],
) -> QuerySpec:
    """Assemble a :class:`QuerySpec` honouring the many → one join direction.

    Primary-key columns of the main table are always included (needed to update
    and delete rows). Each related table must be on the "one" side of a detected
    FK; invalid related tables are skipped. Related columns are read-only and
    aliased to avoid name collisions.
    """
    pk_cols = get_primary_key(metadata, main_table)
    selected = list(dict.fromkeys([*pk_cols, *main_cols]))  # pk first, de-duplicated
    columns = [Column(table=main_table, name=name, alias=name) for name in selected]

    related: list[Related] = []
    main = resolve_table(metadata, main_table)
    for rtable in dict.fromkeys(related_tables):
        target = resolve_table(metadata, rtable)
        matches = [
            constraint
            for constraint in main.foreign_key_constraints
            if constraint.referred_table is target
        ]
        if len(matches) > 1 or target is main:
            raise ValueError(f"Choose an unambiguous lookup table for {rtable}.")
        if not matches:  # not on the "one" side -> reject (would duplicate main rows)
            continue
        fk = matches[0].elements[0]
        related.append(
            Related(table=rtable, local_col=fk.parent.name, remote_col=fk.column.name)
        )
        for col in get_columns(metadata, rtable):
            columns.append(
                Column(table=rtable, name=col.name, alias=f"{rtable}_{col.name}")
            )
    return QuerySpec(main_table=main_table, columns=columns, related=related)
