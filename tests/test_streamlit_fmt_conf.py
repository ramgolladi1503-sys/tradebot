import ast
from pathlib import Path


def _load_fmt_conf():
    path = Path("dashboard/streamlit_app.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "fmt_conf":
            fn_node = node
            break
    assert fn_node is not None, "fmt_conf not found in streamlit_app.py"

    module_ast = ast.Module(
        body=[
            ast.Import(names=[ast.alias(name="math", asname=None)]),
            fn_node,
        ],
        type_ignores=[],
    )
    code = compile(ast.fix_missing_locations(module_ast), str(path), "exec")
    ns = {}
    exec(code, ns, ns)
    return ns["fmt_conf"]


def test_fmt_conf_none_returns_na():
    fmt_conf = _load_fmt_conf()
    assert fmt_conf(None) == "n/a"


def test_fmt_conf_numeric_formats_to_2dp():
    fmt_conf = _load_fmt_conf()
    assert fmt_conf(0.1234) == "0.12"
