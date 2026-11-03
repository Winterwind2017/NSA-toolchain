"""字段级参数校验（借鉴 CAD-Agent-Hub 的 contracts.py 风格）。

好处是错误信息直接点名参数，而不是在深层 COM 调用里炸出一句
`invalid argument`。用法：

    from .contracts import ContractError, require_positive, require_int

    def validate(args):
        require_positive(args.get("size", 0.02), "size")

校验失败统一抛 :class:`ContractError`，内核会把它变成
``{ok: false, errors: ["size must be > 0 (got -1)"]}``，而不是 500 栈。
"""

from __future__ import annotations


class ContractError(ValueError):
    """参数不符合契约。"""


def _show(value) -> str:
    if isinstance(value, float):
        return "%.6g" % value
    return repr(value)


def require_present(value, name: str):
    if value is None:
        raise ContractError("%s is required (got None)" % name)
    if isinstance(value, str) and not value.strip():
        raise ContractError("%s must be a non-empty string" % name)
    return value


def require_positive(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ContractError("%s must be a number (got %s)" % (name, _show(value)))
    if not number > 0:
        raise ContractError("%s must be > 0 (got %s)" % (name, _show(number)))
    return number


def require_non_negative(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ContractError("%s must be a number (got %s)" % (name, _show(value)))
    if number < 0:
        raise ContractError("%s must be >= 0 (got %s)" % (name, _show(number)))
    return number


def require_int(value, name: str, minimum: int | None = None,
                maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            if isinstance(value, bool) or float(value) != int(value):
                raise ValueError
            value = int(value)
        except (TypeError, ValueError):
            raise ContractError("%s must be an integer (got %s)" % (name, _show(value)))
    if minimum is not None and value < minimum:
        raise ContractError("%s must be >= %d (got %d)" % (name, minimum, value))
    if maximum is not None and value > maximum:
        raise ContractError("%s must be <= %d (got %d)" % (name, maximum, value))
    return value


def require_between(value, name: str, low: float, high: float) -> float:
    number = float(value)
    if not low <= number <= high:
        raise ContractError("%s must be within [%s, %s] (got %s)"
                            % (name, _show(low), _show(high), _show(number)))
    return number


def require_enum(value, name: str, choices) -> str:
    choices = tuple(choices)
    if value not in choices:
        raise ContractError("%s must be one of %s (got %s)"
                            % (name, ", ".join(map(str, choices)), _show(value)))
    return value


def validate_against_schema(args: dict, schema: dict) -> None:
    """轻量 JSON-Schema 校验：只查 required / type / enum 三样。

    刻意不做完整实现——目的是把**明显的调用错误**挡在 COM 之前，
    而不是替代 jsonschema。
    """
    if not isinstance(args, dict):
        raise ContractError("arguments must be an object")
    for key in schema.get("required") or []:
        if key not in args or args[key] is None:
            raise ContractError("%s is required" % key)
    props = schema.get("properties") or {}
    type_map = {"string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict}
    for key, spec in props.items():
        if key not in args or args[key] is None:
            continue
        want = spec.get("type")
        if want in type_map:
            got = args[key]
            if want in ("integer", "number") and isinstance(got, bool):
                raise ContractError("%s must be %s (got bool)" % (key, want))
            if not isinstance(got, type_map[want]):
                raise ContractError("%s must be %s (got %s)"
                                    % (key, want, type(got).__name__))
        if "enum" in spec and args[key] not in spec["enum"]:
            raise ContractError("%s must be one of %s (got %s)"
                                % (key, ", ".join(map(str, spec["enum"])), _show(args[key])))
