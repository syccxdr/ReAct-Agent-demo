from typing import Any
import ast
import operator as op
import json
import os


# Safe operators for arithmetic evaluation
_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Num):  # type: ignore[attr-defined]
        return node.n
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Unsupported expression")


def calc(expr: str) -> str:
    expr = expr.strip()
    try:
        node = ast.parse(expr, mode="eval").body
        val = _eval_node(node)  # type: ignore[arg-type]
        return json.dumps({"expr": expr, "result": val})
    except Exception as e:
        return json.dumps({"error": str(e)})


def file_read(path: str) -> str:
    p = path.strip()
    try:
        if not os.path.isabs(p):
            # allow workspace-relative paths
            p = os.path.abspath(p)
        if not os.path.exists(p):
            return json.dumps({"error": f"file not found: {p}"})
        with open(p, "r", encoding="utf-8") as f:
            txt = f.read()
        return json.dumps({
            "path": p,
            "size": len(txt),
            "content_preview": txt[:800]
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def file_write(spec: str) -> str:
    # spec should be JSON: {"path":"...","content":"...","mode":"w"|"a"}
    try:
        j = json.loads(spec)
        path = j["path"]
        content = j.get("content", "")
        mode = j.get("mode", "w")
        if mode not in ("w", "a"):
            return json.dumps({"error": "mode must be 'w' or 'a'"})
        abspath = os.path.abspath(path)
        os.makedirs(os.path.dirname(abspath) or ".", exist_ok=True)
        with open(abspath, mode, encoding="utf-8") as f:
            f.write(content)
        return json.dumps({
            "path": abspath,
            "written": len(content),
            "mode": mode
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


