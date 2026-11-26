"""JS syntax check for generated apps/tools, with a narrow repair for one recurring model glitch.

Some model answers arrive with a literal backslash+n (two characters) between statements, e.g.
    const canvas = document.getElementById('x');\n  const stream = canvas.captureStream();
which node --check rejects ("Invalid or unexpected token") and which used to drop the whole app
("<slug> لم يُبنَ: js syntax error"). The repair only touches a literal \\n that directly follows
`;`, `{` or `}` and is followed by whitespace, and it is kept only when node then accepts the script.
"""
import re
import subprocess
import tempfile

_LITERAL_NL = re.compile(r"([;{}])\\n(?=\s)")


def _node_check(js: str):
    """(ok, stderr). node missing (127) counts as ok, like the callers always did."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
    res = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    return res.returncode in (0, 127), res.stderr


def check_and_repair(spec: dict) -> str:
    """'' when spec['script_js'] parses (after repair, which rewrites spec['script_js']), else 'js syntax error: ...'."""
    js = spec["script_js"]
    ok, err = _node_check(js)
    if ok:
        return ""
    fixed = _LITERAL_NL.sub(r"\1\n", js)
    if fixed != js:
        ok2, _ = _node_check(fixed)
        if ok2:
            spec["script_js"] = fixed
            return ""
    return "js syntax error: " + err[:200]
