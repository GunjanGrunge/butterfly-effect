"""Structure checks for the Butterfly Effect plugin package.

Checks manifests, front matter, cross references and tool declarations against the rules in
AGENT.md (rules 4, 5, 10 and 13) and the Claude Code plugin documentation for manifest and front matter fields. Assertions are written against rules, not wording.
"""
import ast
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# BUTTERFLY_PLUGIN_ROOT points the test at a scratch copy of the plugin (mutation proofs). It is
# refused by test_root_override_is_explicitly_allowed unless BUTTERFLY_ALLOW_OVERRIDE=1 is also set.
ROOT = os.path.abspath(os.environ.get("BUTTERFLY_PLUGIN_ROOT") or REPO_ROOT)
sys.path.insert(0, os.path.join(ROOT, "mcp"))

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PREFIX = "mcp__plugin_butterfly-effect_butterfly__"
ENGINE_TOOLS = {"run_simulation", "compare_options", "generate_test_matrix"}
SKILLS = {"butterfly-interview", "butterfly-report", "butterfly-research", "butterfly-test-design"}
AGENTS = {"timeline-simulator", "test-designer"}
COMMANDS = {"butterfly", "butterfly-test"}


def p(*parts):
    return os.path.join(ROOT, *parts)


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def split_front_matter(path):
    text = read(path)
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "%s: missing or unterminated YAML front matter (--- ... ---)" % os.path.relpath(path, ROOT)
    return m.group(1), text[m.end():]


def parse_front_matter(path):
    raw, _body = split_front_matter(path)
    rel = os.path.relpath(path, ROOT)
    if yaml is not None:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            pytest.fail("%s: front matter is not valid YAML: %s" % (rel, e))
    else:  # minimal strict fallback: top-level 'key: value' and '- item' lists only
        data, key = {}, None
        for line in raw.splitlines():
            if not line.strip():
                continue
            if line.startswith("  - ") or line.startswith("- "):
                assert key is not None, "%s: list item before a key" % rel
                data.setdefault(key, [])
                assert isinstance(data[key], list), "%s: mixed value and list for %s" % (rel, key)
                data[key].append(line.split("- ", 1)[1].strip().strip('"'))
                continue
            m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
            assert m, "%s: unparseable front matter line %r" % (rel, line)
            key = m.group(1)
            val = m.group(2).strip()
            data[key] = val.strip('"') if val else []
    assert isinstance(data, dict), "%s: front matter must be a mapping" % rel
    return data


def _split_depth0(text, is_sep):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and is_sep(ch):
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [x.strip() for x in parts if x.strip()]


def tool_list(value):
    """Normalise a tools / allowed-tools value (YAML list or string) to a list of entries.

    A parenthesised argument may contain spaces and commas, so strings are split on commas at
    depth 0; a string with no depth-0 comma is split on whitespace at depth 0.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value)
    items = _split_depth0(text, lambda c: c == ",")
    if len(items) > 1:
        return items
    return _split_depth0(text, str.isspace)


def files(kind):
    if kind == "commands":
        d = p("commands")
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".md"))
    if kind == "agents":
        d = p("agents")
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".md"))
    d = p("skills")
    return sorted(os.path.join(d, n, "SKILL.md") for n in os.listdir(d)
                  if os.path.isdir(os.path.join(d, n)))


def all_plugin_text_files():
    out = [p(".mcp.json"), p(".claude-plugin", "plugin.json")]
    out += files("commands") + files("agents") + files("skills")
    return out


def registered_engine_tools():
    """Tool names registered with @mcp.tool in server.py, read from its AST."""
    tree = ast.parse(read(p("mcp", "butterfly_mcp", "server.py")))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                target = d.func if isinstance(d, ast.Call) else d
                if isinstance(target, ast.Attribute) and target.attr == "tool":
                    names.add(node.name)
    return names


# ---------------------------------------------------------------- manifests

def test_plugin_json_parses_and_is_named_butterfly_effect():
    data = json.loads(read(p(".claude-plugin", "plugin.json")))
    assert data.get("name") == "butterfly-effect", "plugin.json name must be exactly 'butterfly-effect', got %r" % data.get("name")


def test_mcp_json_server_definition():
    data = json.loads(read(p(".mcp.json")))
    servers = data.get("mcpServers", data)
    assert "butterfly" in servers, ".mcp.json must define a server named 'butterfly'; found %s" % list(servers)
    s = servers["butterfly"]
    assert s.get("command"), ".mcp.json butterfly server needs a command"
    assert isinstance(s.get("args"), list) and s["args"], ".mcp.json butterfly server needs non-empty args"
    pp = s.get("env", {}).get("PYTHONPATH", "")
    assert "${CLAUDE_PLUGIN_ROOT}/mcp" in pp, "PYTHONPATH must use ${CLAUDE_PLUGIN_ROOT}/mcp, got %r" % pp


BS = re.escape(chr(92))   # one literal backslash, escaped for a regex
MACHINE_PATH = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:(?:%s|/(?!/))"      # drive letter, not part of a word or a URL scheme
    r"|(?<![A-Za-z0-9_.:/-])/(?:Users|home|tmp)/"      # POSIX absolute paths
    r"|%sUsers%s" % (BS, BS, BS))


def find_machine_path(text):
    """Return the first absolute machine path found in text, or None. URLs are not paths."""
    m = MACHINE_PATH.search(text)
    return m.group(0) if m else None


MANIFESTS = (".mcp.json", os.path.join(".claude-plugin", "plugin.json"),
             os.path.join(".claude-plugin", "marketplace.json"))


def test_no_absolute_machine_paths_in_manifests():
    for rel in MANIFESTS:
        path = p(*rel.split(os.sep))
        assert os.path.isfile(path), "manifest %s is missing" % rel
        hit = find_machine_path(read(path))
        assert not hit, "%s contains an absolute machine path (%r)" % (rel, hit)


@pytest.mark.parametrize("text", [
    "C:" + chr(92) + "Users" + chr(92) + "x", "c:/work", "D:" + chr(92) + "a", "/Users/me/x", "/home/me", "/tmp/x",
    '{"a": "C:' + chr(92) * 2 + 'Users' + chr(92) * 2 + 'x"}'])
def test_machine_path_checker_flags_real_paths(text):
    assert find_machine_path(text), "checker failed to flag %r" % text


@pytest.mark.parametrize("text", [
    "https://github.com/a/b", "http://example.org", "git+https://x", "write to me: mailto:a@b.org",
    '{"homepage": "https://github.com/GunjanGrunge/butterfly-effect", "name": "x"}',
    "https://github.com/home/x/tmp/y", "version: 1"])
def test_machine_path_checker_ignores_urls_and_text(text):
    assert find_machine_path(text) is None, "false positive on %r" % text


# ---------------------------------------------------------------- inventory and front matter

def test_expected_components_exist_and_nothing_else():
    assert {os.path.basename(f)[:-3] for f in files("commands")} == COMMANDS
    assert {os.path.basename(f)[:-3] for f in files("agents")} == AGENTS
    assert {os.path.basename(os.path.dirname(f)) for f in files("skills")} == SKILLS


def test_skill_files_are_named_exactly_SKILL_md():
    for name in SKILLS:
        d = p("skills", name)
        assert "SKILL.md" in os.listdir(d), "skills/%s must contain a file named exactly SKILL.md, found %s" % (name, os.listdir(d))
        stray = [n for n in os.listdir(d) if n.lower() == "skill.md" and n != "SKILL.md"]
        assert not stray, "skills/%s has wrongly cased skill file %s" % (name, stray)


@pytest.mark.parametrize("path", files("commands"), ids=os.path.basename)
def test_command_front_matter(path):
    fm = parse_front_matter(path)
    for field in ("description", "argument-hint", "allowed-tools"):
        assert fm.get(field), "%s: front matter field %r missing or empty" % (os.path.relpath(path, ROOT), field)


@pytest.mark.parametrize("path", files("agents"), ids=os.path.basename)
def test_agent_front_matter(path):
    fm = parse_front_matter(path)
    for field in ("name", "description", "tools"):
        assert fm.get(field), "%s: front matter field %r missing or empty" % (os.path.relpath(path, ROOT), field)
    assert fm["name"] == os.path.basename(path)[:-3], "%s: name must equal the file name" % path


@pytest.mark.parametrize("path", files("skills"), ids=lambda x: os.path.basename(os.path.dirname(x)))
def test_skill_front_matter(path):
    fm = parse_front_matter(path)
    rel = os.path.relpath(path, ROOT)
    assert fm.get("name"), "%s: 'name' missing" % rel
    assert fm["name"] == os.path.basename(os.path.dirname(path)), "%s: name must equal its folder name" % rel
    assert fm.get("description"), "%s: 'description' missing" % rel
    assert "Use when" in fm["description"], "%s: description must contain the words 'Use when'" % rel


# ---------------------------------------------------------------- cross references

def test_every_referenced_component_exists():
    known = SKILLS | AGENTS | COMMANDS
    problems = []
    for path in all_plugin_text_files():
        text = read(path)
        rel = os.path.relpath(path, ROOT)
        for m in re.finditer(r"butterfly-effect:([A-Za-z][\w-]*)", text):
            if m.group(1) not in known:
                problems.append("%s: references unknown component butterfly-effect:%s" % (rel, m.group(1)))
        for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)", text):
            target = m.group(1).rstrip(".")
            if not os.path.exists(p(*target.split("/"))):
                problems.append("%s: references missing file ${CLAUDE_PLUGIN_ROOT}/%s" % (rel, target))
        # backticked skill/agent/command names, with or without a leading slash
        for m in re.finditer(r"`/?((?:butterfly-[a-z-]+|timeline-simulator|test-designer))`", text):
            n = m.group(1)
            if n not in known and n != "butterfly-effect":
                problems.append("%s: references unknown component `%s`" % (rel, n))
    assert not problems, "\n".join(problems)


def test_every_known_component_is_referenced_by_a_file_that_exists():
    # the three skill folders and two agents referenced by commands/skills must resolve to real files
    for n in SKILLS:
        assert os.path.isfile(p("skills", n, "SKILL.md")), "missing skills/%s/SKILL.md" % n
    for n in AGENTS:
        assert os.path.isfile(p("agents", n + ".md")), "missing agents/%s.md" % n
    for n in COMMANDS:
        assert os.path.isfile(p("commands", n + ".md")), "missing commands/%s.md" % n


# ---------------------------------------------------------------- tool names

def all_tool_entries():
    """(relative path, field, entry) for every tool list in commands, agents and skills."""
    out = []
    for kind, field in (("commands", "allowed-tools"), ("agents", "tools"), ("skills", "allowed-tools")):
        for path in files(kind):
            fm = parse_front_matter(path)
            for entry in tool_list(fm.get(field)):
                out.append((os.path.relpath(path, ROOT), field, entry))
    return out


def test_server_registers_exactly_the_engine_tools():
    assert registered_engine_tools() == ENGINE_TOOLS, "server.py registers %s" % sorted(registered_engine_tools())


def test_engine_tool_names_are_correct_and_registered():
    registered = registered_engine_tools()
    for rel, field, entry in all_tool_entries():
        if "butterfly" in entry and entry.startswith("mcp__"):
            assert entry.startswith(PREFIX), "%s %s: %r must start with %s" % (rel, field, entry, PREFIX)
            tool = entry[len(PREFIX):]
            assert tool in ENGINE_TOOLS and tool in registered, "%s %s: %r is not a registered engine tool" % (rel, field, entry)


def test_wrong_engine_spelling_appears_nowhere():
    for path in all_plugin_text_files():
        assert "mcp__butterfly__" not in read(path), "%s uses the wrong tool spelling 'mcp__butterfly__'" % os.path.relpath(path, ROOT)


def test_no_bare_wildcard_in_any_tool_list():
    for rel, field, entry in all_tool_entries():
        assert "*" not in entry, "%s %s: entry %r contains a wildcard '*', which is not allowed" % (rel, field, entry)


def test_research_skill_allows_only_web_tools():
    fm = parse_front_matter(p("skills", "butterfly-research", "SKILL.md"))
    assert sorted(tool_list(fm.get("allowed-tools"))) == ["WebFetch", "WebSearch"], "research skill allowed-tools: %r" % fm.get("allowed-tools")


def test_test_design_skill_preapproves_only_generate_test_matrix():
    fm = parse_front_matter(p("skills", "butterfly-test-design", "SKILL.md"))
    assert tool_list(fm.get("allowed-tools")) == [PREFIX + "generate_test_matrix"], "test-design allowed-tools: %r" % fm.get("allowed-tools")


def test_no_skill_preapproves_chrome_tools():
    for path in files("skills"):
        fm = parse_front_matter(path)
        bad = [t for t in tool_list(fm.get("allowed-tools")) if t.startswith("mcp__claude-in-chrome__")]
        assert not bad, "%s pre-approves Chrome tools: %s" % (os.path.relpath(path, ROOT), bad)


def test_timeline_simulator_has_exactly_the_two_simulation_tools():
    fm = parse_front_matter(p("agents", "timeline-simulator.md"))
    assert sorted(tool_list(fm.get("tools"))) == sorted([PREFIX + "run_simulation", PREFIX + "compare_options"])


def test_test_designer_has_no_write_edit_or_bash():
    fm = parse_front_matter(p("agents", "test-designer.md"))
    tools = tool_list(fm.get("tools"))
    for forbidden in ("Write", "Edit", "Bash", "MultiEdit", "NotebookEdit"):
        assert forbidden not in tools, "test-designer must not have %s; tools=%s" % (forbidden, tools)
    assert PREFIX + "generate_test_matrix" in tools


# AGENT.md rule 13 was amended on 2026-11-09 with the user's approval; this test matches the
# current rule: commands keep WebSearch and WebFetch pre-approved, no Chrome (mcp__claude-in-chrome__)
# tool is pre-approved anywhere, and no agent gets web or browser tools. If rule 13 changes again,
# update this test together with it; do not loosen it silently.
def test_research_tool_declarations_follow_current_decision():
    for path in files("commands"):
        fm = parse_front_matter(path)
        tools = tool_list(fm.get("allowed-tools"))
        rel = os.path.relpath(path, ROOT)
        assert "WebSearch" in tools and "WebFetch" in tools, "%s: must declare WebSearch and WebFetch (AGENT.md rule 13 as amended); has %s" % (rel, tools)
        chrome = [t for t in tools if t.startswith("mcp__claude-in-chrome__")]
        assert not chrome, "%s: must not pre-approve Chrome tools (AGENT.md rule 13 as amended 2026-11-09): %s" % (rel, chrome)
    for path in files("agents"):
        tools = tool_list(parse_front_matter(path).get("tools"))
        rel = os.path.relpath(path, ROOT)
        web = [t for t in tools if t in ("WebSearch", "WebFetch") or t.startswith("mcp__claude-in-chrome__")]
        assert not web, "%s: agents get no web or Chrome tools (AGENT.md rule 13 as amended): %s" % (rel, web)


# ---------------------------------------------------------------- exact allow-lists

ENGINE_ENTRIES = {PREFIX + t for t in ENGINE_TOOLS}
COMMAND_ALLOWED = {"WebSearch", "WebFetch"} | ENGINE_ENTRIES | {
    "Agent(butterfly-effect:timeline-simulator)", "Agent(butterfly-effect:test-designer)"}
AGENT_EXACT = {
    "timeline-simulator": {PREFIX + "run_simulation", PREFIX + "compare_options"},
    "test-designer": {"Read", "Glob", "Grep", PREFIX + "generate_test_matrix"},
}
SKILL_EXACT = {
    "butterfly-research": {"WebSearch", "WebFetch"},
    "butterfly-test-design": {PREFIX + "generate_test_matrix"},
    "butterfly-interview": set(),
    "butterfly-report": set(),
}


@pytest.mark.parametrize("path", files("commands"), ids=os.path.basename)
def test_command_allowed_tools_are_within_the_allow_list(path):
    tools = tool_list(parse_front_matter(path).get("allowed-tools"))
    rel = os.path.relpath(path, ROOT)
    extra = [t for t in tools if t not in COMMAND_ALLOWED]
    assert not extra, "%s: allowed-tools has entries outside the approved list: %s (allowed: %s)" % (rel, extra, sorted(COMMAND_ALLOWED))
    assert len(tools) == len(set(tools)), "%s: duplicate allowed-tools entries: %s" % (rel, tools)


@pytest.mark.parametrize("name", sorted(AGENT_EXACT))
def test_agent_tools_are_exact(name):
    tools = tool_list(parse_front_matter(p("agents", name + ".md")).get("tools"))
    assert sorted(tools) == sorted(AGENT_EXACT[name]), "agents/%s.md tools %s != exactly %s" % (name, sorted(tools), sorted(AGENT_EXACT[name]))


@pytest.mark.parametrize("name", sorted(SKILL_EXACT))
def test_skill_allowed_tools_are_exact(name):
    tools = tool_list(parse_front_matter(p("skills", name, "SKILL.md")).get("allowed-tools"))
    assert sorted(tools) == sorted(SKILL_EXACT[name]), "skills/%s allowed-tools %s != exactly %s" % (name, sorted(tools), sorted(SKILL_EXACT[name]))


def test_tool_list_parsing_is_robust():
    assert tool_list("Read, Bash(rm -rf *), WebSearch") == ["Read", "Bash(rm -rf *)", "WebSearch"]
    assert tool_list("Bash(git log, git diff) WebFetch") == ["Bash(git log, git diff)", "WebFetch"]
    assert tool_list(["A", "Bash(x y)"]) == ["A", "Bash(x y)"]


def test_root_override_is_explicitly_allowed():
    """Fails if BUTTERFLY_PLUGIN_ROOT points away from this repository without BUTTERFLY_ALLOW_OVERRIDE=1."""
    if ROOT != REPO_ROOT:
        assert os.environ.get("BUTTERFLY_ALLOW_OVERRIDE") == "1", (
            "BUTTERFLY_PLUGIN_ROOT=%s differs from this repository (%s); set BUTTERFLY_ALLOW_OVERRIDE=1 "
            "only for scratch-copy mutation checks" % (ROOT, REPO_ROOT))


# ---------------------------------------------------------------- launcher (integration review M6)

def _butterfly_server_def():
    data = json.loads(read(p(".mcp.json")))
    return data.get("mcpServers", data)["butterfly"]


def test_mcp_json_launcher_is_the_sys_path_cleaning_bootstrap():
    s = _butterfly_server_def()
    assert s["command"] == "python", ".mcp.json command must be 'python', got %r" % s["command"]
    args = s["args"]
    assert args and args[0] == "-c", ".mcp.json args must start with '-c' (not '-m', which puts the working folder first on sys.path); got %r" % args[:1]
    assert len(args) == 2, "expected exactly ['-c', <bootstrap>], got %d args" % len(args)
    boot = args[1]
    assert "runpy" in boot and "butterfly_mcp.server" in boot, "bootstrap must run butterfly_mcp.server through runpy"
    assert "sys.path" in boot and "getcwd" in boot, "bootstrap must remove the working folder from sys.path"
    assert s["env"]["PYTHONPATH"] == "${CLAUDE_PLUGIN_ROOT}/mcp", "PYTHONPATH env must be ${CLAUDE_PLUGIN_ROOT}/mcp"
    assert not find_machine_path(json.dumps(s)), "absolute machine path in .mcp.json"


def _read_line(proc, timeout):
    """Read one line from proc.stdout with a timeout (a reader thread, so a hung server cannot hang the test)."""
    import threading
    box = []
    t = threading.Thread(target=lambda: box.append(proc.stdout.readline()), daemon=True)
    t.start()
    t.join(timeout)
    assert box, "timed out after %ss waiting for a server reply" % timeout
    return box[0]


def _rpc(proc, payload, want_id=None, timeout=20):
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    proc.stdin.flush()
    if want_id is None:
        return None
    while True:
        line = _read_line(proc, timeout)
        if not line:
            try:
                proc.wait(timeout=5)
                err = proc.stderr.read().decode("utf-8", "replace")[-1500:]
            except Exception:
                err = "<stderr unavailable>"
            pytest.fail("server closed stdout before answering id %s (a planted file in the working "
                        "folder probably ran); stderr:\n%s" % (want_id, err))
        msg = json.loads(line)
        if msg.get("id") == want_id:
            return msg


def _hostile_folder(tmp_path, with_stdlib_shadows):
    d = tmp_path / ("hostile_full" if with_stdlib_shadows else "hostile_mcp_only")
    d.mkdir()
    planted = "import sys\n" "sys.stderr.write('PLANTED' + chr(10))\n" "raise SystemExit(3)\n"
    if with_stdlib_shadows:
        (d / "random.py").write_text(planted)
        (d / "typing.py").write_text(planted)
    (d / "mcp").mkdir()
    (d / "mcp" / "__init__.py").write_text(planted)
    return d


@pytest.mark.parametrize("with_stdlib_shadows", [True, False], ids=["random+typing+mcp", "mcp-only"])
def test_launcher_ignores_planted_files_in_the_working_folder(tmp_path, with_stdlib_shadows):
    import subprocess
    s = _butterfly_server_def()
    root_for_json = ROOT
    args = [a.replace("${CLAUDE_PLUGIN_ROOT}", root_for_json) for a in s["args"]]
    env = dict(os.environ)
    env["PYTHONPATH"] = s["env"]["PYTHONPATH"].replace("${CLAUDE_PLUGIN_ROOT}", root_for_json)
    env.pop("PYTHONSAFEPATH", None)
    cwd = _hostile_folder(tmp_path, with_stdlib_shadows)
    proc = subprocess.Popen([sys.executable] + args, cwd=str(cwd), env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "structure-test", "version": "0"}}}, want_id=1)
        assert init["result"]["serverInfo"]["name"] == "butterfly", "initialize reply: %r" % init
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, want_id=2)
        names = {t["name"] for t in tools["result"]["tools"]}
        assert names == ENGINE_TOOLS, "tools/list returned %s" % sorted(names)
        proc.stdin.close()
        rc = proc.wait(timeout=15)
        err = proc.stderr.read().decode("utf-8", "replace")
        assert "PLANTED" not in err, "a planted file in the working folder ran inside the server:\n" + err
        assert rc == 0, "server exit code %r when stdin closed; stderr:\n%s" % (rc, err)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass
