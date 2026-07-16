"""Safe, limited expression evaluator for computed Sheet columns.

Formulas reference other columns of the same row by name and support a small
whitelist of operators and functions. Arbitrary code execution is impossible:
the AST is walked and any node outside the whitelist is rejected (no attribute
access, no arbitrary calls, no names other than provided columns / functions).
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable

# Allowed binary / unary / comparison operators.
_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_CMP_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

# Whitelisted callables usable inside formulas.
_FUNCS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": lambda *a: sum(a[0]) if len(a) == 1 and _iterable(a[0]) else sum(a),
    "len": len,
    "int": int,
    "float": float,
}


def _iterable(value: Any) -> bool:
    try:
        iter(value)
        return not isinstance(value, (str, bytes))
    except TypeError:
        return False


class FormulaError(ValueError):
    """Raised when a formula is invalid or uses a disallowed construct."""


def _num(value: Any) -> Any:
    """Coerce numeric-looking strings to float; leave other values untouched."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _eval(node: ast.AST, row: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, row)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in row:
            return _num(row[node.id])
        raise FormulaError(f"Colonna sconosciuta: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise FormulaError("Operatore non ammesso.")
        return op(_eval(node.left, row), _eval(node.right, row))
    if isinstance(node, ast.UnaryOp):
        unary = _UNARY_OPS.get(type(node.op))
        if unary is None:
            raise FormulaError("Operatore unario non ammesso.")
        return unary(_eval(node.operand, row))
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, row) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row)
        for op_node, comparator in zip(node.ops, node.comparators):
            cmp = _CMP_OPS.get(type(op_node))
            if cmp is None:
                raise FormulaError("Confronto non ammesso.")
            right = _eval(comparator, row)
            if not cmp(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return (
            _eval(node.body, row) if _eval(node.test, row) else _eval(node.orelse, row)
        )
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise FormulaError("Funzione non ammessa.")
        if node.keywords:
            raise FormulaError("Argomenti nominati non ammessi.")
        args = [_eval(a, row) for a in node.args]
        return _FUNCS[node.func.id](*args)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, row) for e in node.elts]
    raise FormulaError("Espressione non ammessa.")


def evaluate(expression: str, row: dict[str, Any]) -> Any:
    """Evaluate ``expression`` against ``row`` (column name -> value).

    Raises :class:`FormulaError` for invalid or disallowed expressions.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Sintassi non valida: {exc.msg}") from exc
    return _eval(tree, row)
