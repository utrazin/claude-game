"""Evaluation of native Blockbench keyframe curves (linear, step, Catmull-Rom, Bezier, Molang numbers).

Shared by GLB delivery and by IK, which needs the animated pose of a chain's parents at any time.
"""
from __future__ import annotations

import ast
import math
import operator


_MATH_FUNCTIONS = {
    "abs": abs, "ceil": math.ceil, "floor": math.floor, "round": round,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "exp": math.exp, "ln": math.log,
    "min": min, "max": max, "pow": pow,
    "lerp": lambda start, end, amount: start + (end - start) * amount,
    "hermite_blend": lambda value: value * value * (3 - 2 * value),
    "clamp": lambda value, low, high: max(low, min(high, value)),
}
_BINARY_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _expression_value(value, *, time, previous):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
    elif isinstance(value, str):
        source = value.strip()
        if source.startswith("return "):
            source = source[7:].strip().rstrip(";").strip()
        source = source.replace("query.anim_time", "query_anim_time").replace("query.life_time", "query_life_time")
        source = source.replace("math.", "math_")
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Unsupported Blockbench animation expression {value!r}") from exc

        def evaluate(node):
            if isinstance(node, ast.Expression):
                return evaluate(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            if isinstance(node, ast.Name):
                names = {"query_anim_time": time, "query_life_time": time, "this": previous}
                if node.id in names:
                    return names[node.id]
                if node.id in {"pi", "math_pi"}:
                    return math.pi
                if node.id in {"e", "math_e"}:
                    return math.e
                raise ValueError(f"Animation expression {value!r} needs unavailable variable {node.id!r}")
            if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
                return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
            if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
                return _BINARY_OPERATORS[type(node.op)](evaluate(node.left), evaluate(node.right))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id.removeprefix("math_")
                function = _MATH_FUNCTIONS.get(name)
                if function is None or node.keywords:
                    raise ValueError(f"Unsupported function in animation expression {value!r}")
                return function(*(evaluate(arg) for arg in node.args))
            raise ValueError(f"Unsupported Blockbench animation expression {value!r}")

        try:
            result = float(evaluate(tree))
        except (ArithmeticError, TypeError, OverflowError) as exc:
            raise ValueError(f"Could not evaluate Blockbench animation expression {value!r}") from exc
    else:
        raise ValueError(f"Invalid animation value {value!r}")
    if not math.isfinite(result):
        raise ValueError("Animation values must be finite numeric values")
    return result


def sample(keys, time, *, previous=(0.0, 0.0, 0.0), context="animation"):
    """Value of one channel's keyframes at ``time``, as Blockbench interpolates them."""
    keys = sorted(keys, key=lambda key: key["time"])
    def value(key):
        point = key["data_points"][0]
        values = []
        for index, axis in enumerate("xyz"):
            try:
                values.append(_expression_value(point[axis], time=time, previous=previous[index]))
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{context}, axis {axis}: {exc}") from exc
        return values
    if time <= keys[0]["time"]:
        return value(keys[0])
    if time >= keys[-1]["time"]:
        return value(keys[-1])
    for index, (a, b) in enumerate(zip(keys, keys[1:])):
        if a["time"] <= time < b["time"]:
            av, bv = value(a), value(b)
            mode = a.get("interpolation", "linear")
            if mode == "step":
                return av
            fraction = (time-a["time"]) / (b["time"]-a["time"])
            if mode == "bezier":
                result = []
                gap = b["time"] - a["time"]
                for axis_index, (left, right) in enumerate(zip(av, bv)):
                    right_time = float(a.get("bezier_right_time", [0, 0, 0])[axis_index] or 0)
                    left_time = float(b.get("bezier_left_time", [0, 0, 0])[axis_index] or 0)
                    right_value = float(a.get("bezier_right_value", [0, 0, 0])[axis_index] or 0)
                    left_value = float(b.get("bezier_left_value", [0, 0, 0])[axis_index] or 0)
                    x0, x1 = a["time"], b["time"]
                    p0 = left
                    p1 = left + right_value
                    p2 = right + left_value
                    x1_handle = x0 + max(0.0, min(gap, right_time))
                    x2_handle = b["time"] + max(-gap, min(0.0, left_time))
                    low, high = 0.0, 1.0
                    for _ in range(32):
                        t = (low + high) / 2
                        inverse = 1 - t
                        x = inverse**3*x0 + 3*inverse**2*t*x1_handle + 3*inverse*t**2*x2_handle + t**3*b["time"]
                        if x < time:
                            low = t
                        else:
                            high = t
                    t = (low + high) / 2
                    inverse = 1 - t
                    result.append(inverse**3*p0 + 3*inverse**2*t*p1 + 3*inverse*t**2*p2 + t**3*right)
                return result
            if mode == "catmullrom":
                before_value, following = value(keys[max(index-1, 0)]), value(keys[min(index+2, len(keys)-1)])
                t, t2, t3 = fraction, fraction**2, fraction**3
                return [.5*((2*v)+(-p+n)*t+(2*p-5*v+4*n-f)*t2+(-p+3*v-3*n+f)*t3)
                        for p, v, n, f in zip(before_value, av, bv, following)]
            if mode != "linear":
                raise ValueError(f"Unsupported interpolation {mode!r}")
            return [v+(n-v)*fraction for v, n in zip(av, bv)]
    raise ValueError("Invalid animation key times")
