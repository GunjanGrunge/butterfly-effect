import asyncio
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MCP_DIR = os.path.join(ROOT, "mcp")
sys.path.insert(0, MCP_DIR)

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

TIMEOUT = 60
CALL_TIMEOUT = datetime.timedelta(seconds=30)


def scenario(**over):
    s = {
        "currency": "INR",
        "horizon_months": 12,
        "income": {"monthly": 100000},
        "fixed_commitments": [{"name": "rent", "monthly": 25000}],
        "typical_expenses": {"monthly": 45000},
        "savings": 0,
        "options": [
            {"name": "Zero", "monthly_cost": 0, "upfront": 0, "duration_months": 0},
            {"name": "Car", "monthly_cost": 20000, "upfront": 0, "duration_months": 12},
        ],
        "success_criterion": {"type": "never_below", "balance": 0},
        "runs": 200,
        "seed": 7,
    }
    s.update(over)
    return s


def matrix_spec():
    return {
        "target": "t",
        "strategy": "boundary",
        "parameters": [{"name": "n", "type": "number", "min": 0, "max": 100}],
    }


def with_session(fn, args=None):
    """Launch the server over stdio, run `await fn(session)`, return its result."""
    env = dict(os.environ)
    env["PYTHONPATH"] = MCP_DIR
    params = StdioServerParameters(
        command=sys.executable, args=args or ["-m", "butterfly_mcp.server"], env=env
    )

    async def main():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=CALL_TIMEOUT) as session:
                await session.initialize()
                return await fn(session)

    async def guarded():
        return await asyncio.wait_for(main(), TIMEOUT)

    return asyncio.run(guarded())


def text_of(result):
    return "".join(c.text for c in result.content if c.type == "text")


def test_lists_three_tools():
    async def go(s):
        return await s.list_tools()

    tools = with_session(go).tools
    assert {t.name for t in tools} == {"run_simulation", "compare_options", "generate_test_matrix"}
    gtm = next(t for t in tools if t.name == "generate_test_matrix")
    assert "test_scenario" in gtm.inputSchema["properties"]


def test_compare_options_result_shape():
    async def go(s):
        return await s.call_tool("compare_options", {"scenario": scenario()}, CALL_TIMEOUT)

    res = with_session(go)
    assert not res.isError
    data = json.loads(text_of(res))
    assert {"options", "recommended", "sensitivity", "assumptions", "sensitivity_option", "seed", "method"} <= set(data)
    assert {o["name"] for o in data["options"]} == {"Zero", "Car"}
    assert "confidence_pct" in data["options"][0]


def test_run_simulation_ok():
    async def go(s):
        return await s.call_tool(
            "run_simulation", {"scenario": scenario(), "option_name": "Zero"}, CALL_TIMEOUT
        )

    res = with_session(go)
    assert not res.isError
    assert json.loads(text_of(res))["confidence_pct"] == 100.0


def test_bad_scenario_error_names_field():
    async def go(s):
        return await s.call_tool(
            "compare_options", {"scenario": scenario(horizon_months=0)}, CALL_TIMEOUT
        )

    res = with_session(go)
    assert res.isError
    msg = text_of(res)
    assert "horizon_months" in msg
    assert "Traceback" not in msg


def test_unknown_option_error():
    async def go(s):
        return await s.call_tool(
            "run_simulation", {"scenario": scenario(), "option_name": "Nope"}, CALL_TIMEOUT
        )

    res = with_session(go)
    assert res.isError
    assert "unknown option: Nope" in text_of(res)
    assert "Traceback" not in text_of(res)


def test_generate_test_matrix_returns_cases():
    async def go(s):
        return await s.call_tool("generate_test_matrix", {"test_scenario": matrix_spec()}, CALL_TIMEOUT)

    res = with_session(go)
    assert not res.isError
    data = json.loads(text_of(res))
    assert data["strategy"] == "boundary"
    assert data["cases"]


def test_bad_test_scenario_error_names_field():
    async def go(s):
        bad = matrix_spec()
        bad["strategy"] = "nonsense"
        return await s.call_tool("generate_test_matrix", {"test_scenario": bad}, CALL_TIMEOUT)

    res = with_session(go)
    assert res.isError
    assert "strategy" in text_of(res)


def test_time_limit_error_is_plain_message(monkeypatch):
    import butterfly_mcp.server as server

    def boom(*a, **k):
        raise ValueError("simulation time limit exceeded; reduce runs")

    monkeypatch.setattr(server.engine, "compare_options", boom)
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as e:
        server.compare_options(scenario())
    assert "time limit exceeded" in str(e.value)


def test_import_mcp_resolves_to_installed_sdk_from_project_root():
    code = "import mcp, mcp.server.fastmcp, os; print(os.path.realpath(mcp.__file__))"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, out.stderr
    path = os.path.normcase(os.path.realpath(out.stdout.strip()))
    mcp_dir = os.path.normcase(os.path.realpath(MCP_DIR))
    assert os.path.commonpath([path, mcp_dir]) != mcp_dir


MARKER = 987654321


@pytest.mark.parametrize("bad", [MARKER, str(MARKER), [MARKER], True])
def test_wrong_type_scenario_does_not_echo_input(bad):
    async def go(s):
        return await s.call_tool("compare_options", {"scenario": bad}, CALL_TIMEOUT)

    res = with_session(go)
    assert res.isError
    msg = text_of(res)
    assert str(MARKER) not in msg
    assert "input_value" not in msg and "pydantic" not in msg
    assert "scenario" in msg and "object" in msg


def test_wrong_type_option_name_and_test_scenario_do_not_echo():
    async def go(s):
        a = await s.call_tool("run_simulation", {"scenario": scenario(), "option_name": MARKER}, CALL_TIMEOUT)
        b = await s.call_tool("generate_test_matrix", {"test_scenario": MARKER}, CALL_TIMEOUT)
        return a, b

    for res in with_session(go):
        assert res.isError
        msg = text_of(res)
        assert str(MARKER) not in msg
        assert "input_value" not in msg and "pydantic" not in msg


def test_unexpected_exception_is_generic(monkeypatch):
    import butterfly_mcp.server as server
    from mcp.server.fastmcp.exceptions import ToolError

    def boom(*a, **k):
        raise RuntimeError("secret 987654321")

    monkeypatch.setattr(server.engine, "compare_options", boom)
    with pytest.raises(ToolError) as e:
        server.compare_options(scenario())
    assert str(e.value) == "Unexpected error while processing the request"


def test_random_strategy_with_count_over_stdio():
    spec = matrix_spec()
    spec.update(strategy="random", count=7, seed=3)

    async def go(s):
        return await s.call_tool("generate_test_matrix", {"test_scenario": spec}, CALL_TIMEOUT)

    res = with_session(go)
    assert not res.isError
    data = json.loads(text_of(res))
    assert data["strategy"] == "random" and data["count"] == 7 and len(data["cases"]) == 7


def test_time_guard_error_over_the_wire():
    # Server launched with the engine's time limit forced to 0 s (a real 20 s run is too slow).
    code = (
        "import butterfly_mcp.engine as e; e.TIME_LIMIT_SECONDS = 0; "
        "import butterfly_mcp.server as s; s.main()"
    )

    async def go(s):
        return await s.call_tool("compare_options", {"scenario": scenario()}, CALL_TIMEOUT)

    res = with_session(go, args=["-c", code])
    assert res.isError
    assert "simulation time limit exceeded; reduce runs" in text_of(res)
    assert "Traceback" not in text_of(res)


def test_descriptions_list_fields():
    async def go(s):
        return await s.list_tools()

    d = {t.name: t.description for t in with_session(go).tools}
    for k in ("horizon_months", "variability_pct", "fixed_commitments", "dynamic_events",
              "success_criterion", "never_below", "duration_months"):
        assert k in d["compare_options"] and k in d["run_simulation"]
    for k in ("target", "parameters", "boundary", "equivalence", "pairwise", "random", "count", "cases"):
        assert k in d["generate_test_matrix"]
    assert "not stored or transmitted" in d["generate_test_matrix"]


def test_missing_mcp_package_gives_one_line_on_stderr():
    # Block the mcp package in a throwaway interpreter; the real installation is untouched.
    code = chr(10).join([
        "import sys",
        "class B:",
        "    def find_spec(self, name, path=None, target=None):",
        "        if name == 'mcp' or name.startswith('mcp.'):",
        "            raise ModuleNotFoundError(\"No module named 'mcp'\")",
        "sys.meta_path.insert(0, B())",
        "import runpy; runpy.run_module('butterfly_mcp.server', run_name='__main__')",
    ])
    env = dict(os.environ)
    env["PYTHONPATH"] = MCP_DIR
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode != 0
    assert out.stdout == ""
    assert "Traceback" not in out.stderr
    lines = out.stderr.strip().splitlines()
    assert len(lines) == 1
    assert "'mcp' Python package is required" in lines[0]
    assert lines[0].endswith("Install it with: python -m pip install mcp")
    assert "requirements.txt" not in lines[0]


def _assert_clean(msg, marker=None, arg=None):
    low = msg.lower()
    assert "input_value" not in msg and "pydantic" not in low and "http" not in low
    if marker is not None:
        assert str(marker) not in msg
    if arg is not None:
        assert f"'{arg}'" in msg


def test_missing_required_argument_with_marker_in_wrong_argument():
    async def go(s):
        return await s.call_tool("compare_options", {"savings": MARKER, "income": MARKER}, CALL_TIMEOUT)

    res = with_session(go)
    assert res.isError
    _assert_clean(text_of(res), MARKER, "scenario")


def test_unexpected_extra_argument_carrying_marker():
    async def go(s):
        a = await s.call_tool("compare_options", {"scenario": scenario(), "extra": MARKER}, CALL_TIMEOUT)
        b = await s.call_tool("compare_options", {"extra": MARKER}, CALL_TIMEOUT)
        return a, b

    a, b = with_session(go)
    _assert_clean(text_of(b), MARKER, "scenario")
    assert b.isError
    if a.isError:  # extra arguments may be rejected or ignored, but never echoed
        _assert_clean(text_of(a), MARKER)


def test_all_arguments_missing():
    async def go(s):
        a = await s.call_tool("run_simulation", {}, CALL_TIMEOUT)
        b = await s.call_tool("generate_test_matrix", {}, CALL_TIMEOUT)
        c = await s.call_tool("run_simulation", {"scenario": scenario()}, CALL_TIMEOUT)
        return a, b, c

    a, b, c = with_session(go)
    for res, arg in ((a, "scenario"), (b, "test_scenario"), (c, "option_name")):
        assert res.isError
        _assert_clean(text_of(res), None, arg)


def test_long_unknown_option_name_is_bounded():
    async def go(s):
        return await s.call_tool(
            "run_simulation", {"scenario": scenario(), "option_name": "x" * 100000}, CALL_TIMEOUT
        )

    res = with_session(go)
    assert res.isError
    msg = text_of(res)
    assert msg.startswith("Error executing tool run_simulation: unknown option: ") or "unknown option: " in msg
    assert len(msg) < 200


def test_descriptions_mention_count_limits_and_balance_meaning():
    async def go(s):
        return await s.list_tools()

    d = {t.name: t.description for t in with_session(go).tools}
    assert "1 to 1000" in d["generate_test_matrix"] and "default 20" in d["generate_test_matrix"]
    for n in ("run_simulation", "compare_options"):
        assert "lowest balance" in d[n]


# ---- raw JSON-RPC over stdin/stdout (no SDK client) ----
RAW_MARKER = "123456789"


def _raw_session(lines, expect_ids, wait=15):
    """Start the server, send init + each line in `lines` (str, written verbatim), then a final
    tools/list (id 999). Return (stdout_text, stderr_text). Always terminates the process."""
    import threading

    env = dict(os.environ)
    env["PYTHONPATH"] = MCP_DIR
    proc = subprocess.Popen(
        [sys.executable, "-m", "butterfly_mcp.server"], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    out_chunks, err_chunks = [], []

    def drain(stream, sink):
        for chunk in iter(lambda: stream.read1(65536), b""):
            sink.append(chunk)

    threads = [threading.Thread(target=drain, args=(proc.stdout, out_chunks), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, err_chunks), daemon=True)]
    for t in threads:
        t.start()
    try:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "raw", "version": "0"}}}
        msgs = [json.dumps(init), json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})]
        msgs += lines
        msgs.append(json.dumps({"jsonrpc": "2.0", "id": 999, "method": "tools/list"}))
        for m in msgs:
            proc.stdin.write((m + chr(10)).encode("utf-8"))
            proc.stdin.flush()
        import time
        deadline = time.time() + wait
        while time.time() < deadline and b'"id":999' not in b"".join(out_chunks).replace(b' ', b''):
            time.sleep(0.1)
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        for t in threads:
            t.join(timeout=5)
    return b"".join(out_chunks).decode("utf-8", "replace"), b"".join(err_chunks).decode("utf-8", "replace")


def _call_msg(params, method="tools/call", id_=2):
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})


RAW_CASES = {
    "arguments_list": _call_msg({"name": "compare_options", "arguments": [int(RAW_MARKER)]}),
    "arguments_string": _call_msg({"name": "compare_options", "arguments": "x" + RAW_MARKER}),
    "arguments_nested": _call_msg({"name": "compare_options",
                                   "arguments": {"scenario": {"savings": {"a": [int(RAW_MARKER)]}}}}),
    "malformed_json": '{"jsonrpc": "2.0", "id": 3, "method": ' + RAW_MARKER + " oops",
    "unknown_tool": _call_msg({"name": "nope" + RAW_MARKER, "arguments": {}}),
    "params_string": _call_msg("p" + RAW_MARKER),
    "params_list": _call_msg([int(RAW_MARKER)]),
}


@pytest.mark.parametrize("case", sorted(RAW_CASES))
def test_raw_protocol_abuse_never_leaks_marker_on_stderr(case):
    out, err = _raw_session([RAW_CASES[case]], None)
    assert RAW_MARKER not in err, err[:300]
    assert err.strip() == "", err[:300]
    if case != "unknown_tool":
        assert RAW_MARKER not in out
    # the server stays alive and answers the next valid request
    assert '"id":999' in out.replace(" ", "")


def test_unknown_tool_name_huge_is_silent_on_stderr_and_server_survives():
    # Residual (documented): the SDK echoes an unknown tool NAME uncapped in its stdout error.
    big = _call_msg({"name": "n" * 100000, "arguments": {}})
    out, err = _raw_session([big], None)
    assert err.strip() == ""
    assert '"id":999' in out.replace(" ", "")


def test_descriptions_state_required_argument_first():
    async def go(s):
        return await s.list_tools()

    d = {t.name: t.description for t in with_session(go).tools}
    assert d["run_simulation"].startswith("Required arguments: scenario and option_name")
    assert d["compare_options"].startswith("Required argument: scenario")
    assert d["generate_test_matrix"].startswith("Required argument: test_scenario")


TM_MSG = "test matrix time limit exceeded; reduce the parameters or use the random strategy"


def test_test_matrix_time_guard_over_the_wire():
    code = (
        "import butterfly_mcp.testmatrix as t; t.TIME_LIMIT_SECONDS = 0; "
        "import butterfly_mcp.server as s; s.main()"
    )
    spec = {"target": "t", "strategy": "pairwise", "parameters": [
        {"name": f"p{i}", "type": "enum", "values": list(range(6))} for i in range(6)]}

    async def go(s):
        return await s.call_tool("generate_test_matrix", {"test_scenario": spec}, CALL_TIMEOUT)

    res = with_session(go, args=["-c", code])
    assert res.isError
    assert TM_MSG in text_of(res)
    assert "Traceback" not in text_of(res)


def test_test_matrix_message_is_exact_match_only(monkeypatch):
    import butterfly_mcp.server as server
    from mcp.server.fastmcp.exceptions import ToolError

    def other(*a, **k):
        raise ValueError(TM_MSG + " 987654321")

    monkeypatch.setattr(server.testmatrix, "generate_test_matrix", other)
    with pytest.raises(ToolError) as e:
        server.generate_test_matrix(matrix_spec())
    assert str(e.value) == "Unexpected error while processing the request"


def test_test_matrix_caps_over_stdio():
    many = {"target": "t", "strategy": "boundary", "parameters": [
        {"name": f"p{i}", "type": "number", "min": 0, "max": MARKER} for i in range(51)]}
    big_enum = {"target": "t", "strategy": "boundary", "parameters": [
        {"name": "a", "type": "enum", "values": list(range(10001))}]}

    async def go(s):
        a = await s.call_tool("generate_test_matrix", {"test_scenario": many}, CALL_TIMEOUT)
        b = await s.call_tool("generate_test_matrix", {"test_scenario": big_enum}, CALL_TIMEOUT)
        return a, b

    a, b = with_session(go)
    assert a.isError and "'parameters'" in text_of(a)
    assert b.isError and "parameters[0].values" in text_of(b)
    for r in (a, b):
        assert str(MARKER) not in text_of(r)


def test_duplicate_option_names_and_variability_over_stdio():
    dup = scenario(options=[
        {"name": "Car", "monthly_cost": 1, "upfront": 0, "duration_months": 1},
        {"name": " car ", "monthly_cost": MARKER, "upfront": 0, "duration_months": 1}])
    var = scenario(income={"monthly": 100000, "variability_pct": 150})

    async def go(s):
        a = await s.call_tool("compare_options", {"scenario": dup}, CALL_TIMEOUT)
        b = await s.call_tool("compare_options", {"scenario": var}, CALL_TIMEOUT)
        return a, b

    a, b = with_session(go)
    assert a.isError and "options[1].name" in text_of(a) and "unique" in text_of(a)
    assert b.isError and "income.variability_pct" in text_of(b)
    assert str(MARKER) not in text_of(a)


def test_descriptions_state_units_distinct_names_and_limits():
    async def go(s):
        return await s.list_tools()

    d = {t.name: t.description for t in with_session(go).tools}
    for n in ("run_simulation", "compare_options"):
        assert "percent" in d[n] and "0 to 100" in d[n]
        assert "fraction" in d[n] and "0 to 1" in d[n]
        assert "distinct" in d[n] and "ignoring case" in d[n]
    assert "option_name must match" in d["run_simulation"]
    g = d["generate_test_matrix"]
    for k in ("at most 50 parameters", "1 to 1000", "number", "enum", "time limit"):
        assert k in g


def _tm_call(spec, id_=2):
    return _call_msg({"name": "generate_test_matrix", "arguments": {"test_scenario": spec}}, id_=id_)


def _responses(out):
    res = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if "id" in m:
                res[m["id"]] = m
    return res


def _err_text(resp):
    r = resp["result"]
    assert r["isError"], r
    return "".join(c["text"] for c in r["content"])


def test_oversized_requests_are_rejected_fast_over_stdio():
    import time
    import butterfly_mcp.testmatrix as tm

    pair = {"target": "t", "strategy": "pairwise", "parameters": [
        {"name": f"m{i}", "type": "enum", "values": [f"v{j}" for j in range(3000)]} for i in range(2)]}
    # 12 parameters x 10,000 short values: about 600,000 characters (schema accepts it),
    # but boundary cells = cases x parameters exceed MAX_BOUNDARY_CELLS.
    n_par, n_val = 12, 10000
    assert (n_par * n_val) * n_par > tm.MAX_BOUNDARY_CELLS
    bound = {"target": "t", "strategy": "boundary", "parameters": [
        {"name": f"b{i}", "type": "enum", "values": [f"v{j}" for j in range(n_val)]}
        for i in range(n_par)]}
    t0 = time.monotonic()
    out, err = _raw_session([_tm_call(pair, 2), _tm_call(bound, 3), _tm_call(matrix_spec(), 4)], None)
    assert time.monotonic() - t0 < 30
    r = _responses(out)
    for i, msg in ((2, tm.PAIR_MESSAGE), (3, tm.BOUNDARY_MESSAGE)):
        t = _err_text(r[i])
        assert "'parameters'" in t and msg in t
    assert not r[4]["result"]["isError"]
    assert err.strip() == ""


def test_schema_valid_request_with_huge_output_is_rejected():
    import butterfly_mcp.testmatrix as tm

    params = [{"name": f"{i:02d}" + "n" * 98, "type": "enum", "values": ["a", "b", "c"]}
              for i in range(tm.MAX_PARAMETERS)]
    spec = {"target": "t", "strategy": "random", "count": tm.MAX_RANDOM_COUNT, "parameters": params}
    estimate = tm.MAX_RANDOM_COUNT * tm.MAX_PARAMETERS * (100 + 4 + 3)
    assert estimate > tm.MAX_OUTPUT_CHARS
    out, err = _raw_session([_tm_call(spec, 2), _tm_call(matrix_spec(), 3)], None)
    r = _responses(out)
    t = _err_text(r[2])
    assert "'parameters'" in t and tm.OUTPUT_MESSAGE in t
    assert not r[3]["result"]["isError"]
    assert err.strip() == ""


def test_schema_limit_violations_name_field_and_never_echo_value():
    mk = RAW_MARKER

    def one(param, **over):
        spec = {"target": "t", "strategy": "boundary", "parameters": [param]}
        spec.update(over)
        return spec

    many = {"target": "t", "strategy": "random", "parameters": [
        {"name": f"p{i}", "type": "enum", "values": [f"{mk}-{i}-{j}-" + "x" * 175 for j in range(1000)]}
        for i in range(6)]}
    cases = [
        (one({"name": mk + "n" * 98, "type": "enum", "values": ["a"]}) | {}, "parameters[0].name"),
        (one({"name": "p", "type": "enum", "values": [mk + "x" * 198]}), "parameters[0].values"),
        (one({"name": "p", "type": "enum", "values": [{"k": int(mk)}]}), "parameters[0].values"),
        (one({"name": "p", "type": "number", "min": -1e308, "max": 1e308}), "parameters[0]"),
        (many, "'parameters'"),
    ]
    lines = [_tm_call(spec, 2 + i) for i, (spec, _) in enumerate(cases)]
    lines.append(_tm_call(matrix_spec(), 50))
    out, err = _raw_session(lines, None)
    r = _responses(out)
    for i, (_, field) in enumerate(cases):
        t = _err_text(r[2 + i])
        assert field in t, (i, t)
        assert mk not in t
    assert not r[50]["result"]["isError"]
    assert err.strip() == ""


def test_matrix_description_is_built_from_constants():
    import butterfly_mcp.schema as sc
    import butterfly_mcp.testmatrix as tm
    import butterfly_mcp.server as server

    def has(text, phrase):
        import re
        return re.search(r"(?<![\w,])" + re.escape(phrase) + r"(?!\w)", text) is not None

    d = server.matrix_description()
    assert d.startswith("Required argument: test_scenario")
    for phrase in (
        f"at most {tm.MAX_PARAMETERS} parameters",
        f"at most {tm.MAX_ENUM_VALUES:,} values",
        f"{tm.MAX_PAIRS:,} value pairs",
        f"{tm.MAX_BOUNDARY_CELLS:,} cases x parameters",
        f"{tm.MAX_OUTPUT_CHARS:,} characters of compact JSON",
        "about 2 to 3 times that size",
        "rejected before any cases are built",
        "checked while the cases are built",
        f"count 1 to {tm.MAX_RANDOM_COUNT}",
        f"default {tm.DEFAULT_RANDOM_COUNT}",
        f"{tm.TIME_LIMIT_SECONDS} second time limit",
        f"names at most {sc.MAX_NAME_LENGTH} characters",
        f"enum text at most {sc.MAX_ENUM_VALUE_LENGTH} characters",
        f"{sc.MAX_TOTAL_VALUE_CHARS:,} characters in total",
        "1e15",
        "duplicate enum values are removed for the boundary, equivalence and pairwise strategies",
        "drawn proportionally more often",
    ):
        assert has(d, phrase), phrase

    # changing a constant changes the rendered description, so the check above would fail
    for mod, name, val in ((tm, "TIME_LIMIT_SECONDS", 1), (tm, "MAX_PARAMETERS", 5),
                           (tm, "MAX_PAIRS", 7), (tm, "MAX_OUTPUT_CHARS", 9), (sc, "MAX_NAME_LENGTH", 33)):
        old = getattr(mod, name)
        setattr(mod, name, val)
        try:
            changed = server.matrix_description()
        finally:
            setattr(mod, name, old)
        assert changed != d
        assert not has(changed, {"TIME_LIMIT_SECONDS": f"{old} second",
                                 "MAX_PARAMETERS": f"at most {old} parameters",
                                 "MAX_PAIRS": f"{old:,} value pairs",
                                 "MAX_OUTPUT_CHARS": f"{old:,} characters of compact JSON",
                                 "MAX_NAME_LENGTH": f"names at most {old} characters"}[name])
