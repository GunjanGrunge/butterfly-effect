"""Privacy and determinism checks for mcp/butterfly_mcp (AGENT.md rule 5).

The scan is AST based, so comments and docstrings never cause false positives. Import aliases
(`import os as o`, `from os import system as s`) and simple assignment aliases (`e = exec`) are
resolved before names are checked. The checker is proven to bite by TestCheckerSelfTest before it
is trusted on the real package.

Known limits (an AST scan cannot prove everything): values built at run time and passed to
dynamic lookups, attribute chains on objects returned by calls, and str.replace versus
Path.replace (only os.replace is flagged).
"""
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# BUTTERFLY_PRIVACY_PKG_DIR points the scan at a scratch copy (mutation proofs); it is refused by
# test_package_override_is_explicitly_allowed unless BUTTERFLY_ALLOW_OVERRIDE=1 is also set.
DEFAULT_PKG_DIR = os.path.join(ROOT, "mcp", "butterfly_mcp")
PKG_DIR = os.path.abspath(os.environ.get("BUTTERFLY_PRIVACY_PKG_DIR") or DEFAULT_PKG_DIR)
sys.path.insert(0, os.path.join(ROOT, "mcp"))

import pytest

FORBIDDEN_MODULES = {
    # network and process
    "socket", "ssl", "urllib", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
    "telnetlib", "xmlrpc", "subprocess", "socketserver", "selectors", "poplib", "imaplib",
    "nntplib", "wsgiref", "webbrowser", "asyncore", "asynchat", "http",
    # persistence and file mutation
    "pickle", "shelve", "sqlite3", "dbm", "tempfile", "shutil",
    # dynamic code and low level tricks
    "ctypes", "pty", "marshal", "mmap", "runpy", "code", "codeop", "imp", "builtins",
    # process pools and connections
    "multiprocessing",
}
FORBIDDEN_DOTTED = {"multiprocessing.connection"}
OS_MUTATORS = {"system", "popen", "remove", "unlink", "rename", "replace", "mkdir", "makedirs",
               "write", "open", "truncate", "symlink", "link", "rmdir", "removedirs", "chmod",
               "chown", "startfile", "fork", "kill", "ftruncate", "lchown", "mkfifo", "mknod"}
FORBIDDEN_QUAL = (
    {"os." + n for n in OS_MUTATORS}
    | {"sys.stdout", "sys.__stdout__", "importlib.import_module", "importlib.__import__",
       "logging.FileHandler", "logging.handlers.RotatingFileHandler",
       "logging.handlers.TimedRotatingFileHandler", "logging.handlers.WatchedFileHandler",
       "logging.handlers.FileHandler", "io.FileIO", "os.fdopen",
       "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
       "numpy.save", "numpy.savez", "numpy.savez_compressed", "numpy.savetxt"}
    | {"asyncio." + n for n in (
        "open_connection", "start_server", "create_server", "create_connection",
        "open_unix_connection", "start_unix_server", "create_datagram_endpoint")}
)
FORBIDDEN_QUAL_PREFIXES = ("os.exec", "os.spawn")
FORBIDDEN_BUILTIN_NAMES = {"eval", "exec", "compile", "__import__", "__builtins__"}
FORBIDDEN_ATTR_NAMES = {
    "write_text", "write_bytes", "mkdir", "touch", "unlink", "rmdir", "symlink_to", "hardlink_to",
    "rename", "to_csv", "to_json", "to_excel", "to_pickle", "to_parquet", "to_feather", "to_hdf",
    "to_sql", "to_stata", "to_xml", "to_latex", "savetxt", "savez", "savez_compressed", "tofile",
    "create_server", "create_connection", "open_connection", "start_server",
    "open_unix_connection", "start_unix_server", "create_datagram_endpoint",
}
OPEN_LIKE = {"open", "io.open", "codecs.open", "gzip.open", "bz2.open", "lzma.open", "tarfile.open"}
MODE_AT_1 = OPEN_LIKE | {"zipfile.ZipFile", "tarfile.TarFile", "gzip.GzipFile", "bz2.BZ2File",
                         "lzma.LZMAFile"}


def _is_str_const(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_write_mode(node):
    """True if node is a string constant that looks like a file mode with write intent."""
    if not _is_str_const(node):
        return False
    s = node.value
    return bool(s) and set(s) <= set("rwxabt+U") and any(c in s for c in "wax+")


def _module_forbidden(name):
    return name.split(".")[0] in FORBIDDEN_MODULES or any(
        name == d or name.startswith(d + ".") for d in FORBIDDEN_DOTTED)


def _qual_forbidden(q):
    return q in FORBIDDEN_QUAL or q.startswith(FORBIDDEN_QUAL_PREFIXES)


def scan_source(source, filename="<snippet>"):
    """Return a list of violation strings for one source text."""
    tree = ast.parse(source, filename=filename)
    found = []
    alias = {}   # local name -> dotted name it stands for
    from_names = set()   # local names bound by "from x import y"

    def add(node, msg):
        m = "%s:%d: %s" % (filename, getattr(node, "lineno", 0), msg)
        if m not in found:
            found.append(m)

    def qual(node):
        if isinstance(node, ast.Name):
            return alias.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = qual(node.value)
            return base + "." + node.attr if base else None
        return None

    # pass 1: imports (module and from-import aliases)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    alias[a.asname] = a.name
                if _module_forbidden(a.name) or _qual_forbidden(a.name):
                    add(node, "forbidden import %s" % a.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mod = node.module or ""
            if _module_forbidden(mod):
                add(node, "forbidden import from %s" % mod)
            for a in node.names:
                full = mod + "." + a.name
                alias[a.asname or a.name] = full
                from_names.add(a.asname or a.name)
                if _module_forbidden(full) or _qual_forbidden(full):
                    add(node, "forbidden import %s" % full)
                if mod == "random" and a.name != "Random":
                    add(node, "global random function imported: %s" % a.name)
    # pass 2: simple assignment aliases such as e = exec, o = os.system
    for _ in range(2):
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name) \
                    and isinstance(node.value, (ast.Name, ast.Attribute)):
                q = qual(node.value)
                if q:
                    alias.setdefault(node.targets[0].id, q)

    def mode_unsafe(call, name):
        cands = []
        if name in MODE_AT_1 and len(call.args) > 1:
            cands.append(call.args[1])
        cands += [k.value for k in call.keywords if k.arg == "mode"]
        for c in cands:
            if _is_write_mode(c):
                add(call, "%s() with a write, append or exclusive mode %r" % (name, c.value))
            elif not _is_str_const(c):
                add(call, "%s() with a non-literal mode (cannot prove read-only)" % name)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(getattr(node, "ctx", None), ast.Load):
            q = qual(node)
            if q:
                if _qual_forbidden(q):
                    add(node, "forbidden use of %s" % q)
                if q.startswith("random.") and q.count(".") == 1 and q != "random.Random":
                    add(node, "use of global %s (determinism: use random.Random(seed))" % q)
            if isinstance(node, ast.Name) and alias.get(node.id, node.id) in FORBIDDEN_BUILTIN_NAMES:
                add(node, "use of %s" % alias.get(node.id, node.id))
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTR_NAMES:
                add(node, "use of .%s (file mutation or network)" % node.attr)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del))                 and qual(node) in ("sys.stdout", "sys.stderr", "sys.__stdout__", "sys.__stderr__"):
            add(node, "assignment to %s (redirecting a standard stream)" % qual(node))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in from_names                 and alias.get(node.id) in ("sys.stdout", "sys.stderr"):
            add(node, "rebinding of %s imported from sys" % node.id)
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "replace" and len(node.args) == 1 and not node.keywords:
            add(node, ".replace() with one argument (Path.replace moves a file; str.replace needs two)")
        q = qual(f) or ""
        if q in MODE_AT_1:
            mode_unsafe(node, q)
        elif isinstance(f, ast.Attribute) and f.attr == "open":
            # Path.open(mode): the mode is args[0]; a second positional is an io.open-style mode
            if node.args and _is_write_mode(node.args[0]):
                add(node, ".open() with a write mode %r" % node.args[0].value)
            if len(node.args) > 1:
                mode_unsafe(node, "open")
            for k in node.keywords:
                if k.arg == "mode" and not _is_str_const(k.value):
                    add(node, ".open() with a non-literal mode")
                elif k.arg == "mode" and _is_write_mode(k.value):
                    add(node, ".open() with a write mode %r" % k.value.value)
        if q == "print":
            kws = {k.arg: k.value for k in node.keywords}
            if "file" not in kws or qual(kws["file"]) != "sys.stderr":
                add(node, "print() without file=sys.stderr (stdout is the protocol channel)")
        if q == "getattr" and node.args:
            fq = qual(node.args[0]) or ""
            if fq.split(".")[0] in ("__builtins__", "builtins"):
                add(node, "getattr on builtins")
        if q == "logging.basicConfig" and any(
                k.arg in ("filename", "handlers") or k.arg is None for k in node.keywords):
            add(node, "logging.basicConfig with filename/handlers writes files")
        if q in ("fileinput.input", "fileinput.FileInput") and any(
                k.arg == "inplace" and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                for k in node.keywords):
            add(node, "fileinput with inplace edits files")
    return found


def package_sources():
    out = []
    for dirpath, _dirs, files in os.walk(PKG_DIR):
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


BAD_SNIPPETS = {
    "import socket": "import socket",
    "import ssl": "import ssl",
    "import http.client": "import http.client",
    "from http import server": "from http import server",
    "import urllib.request": "import urllib.request",
    "from urllib import parse": "from urllib import parse",
    "import requests": "import requests",
    "import httpx": "import httpx",
    "import aiohttp": "import aiohttp",
    "import ftplib": "import ftplib",
    "import smtplib": "import smtplib",
    "import telnetlib": "import telnetlib",
    "import xmlrpc.client": "import xmlrpc.client",
    "import subprocess": "import subprocess",
    "import pickle": "import pickle",
    "import shelve": "import shelve",
    "import sqlite3": "import sqlite3",
    "import dbm": "import dbm",
    "import tempfile": "from tempfile import mkdtemp",
    "open write positional": "open('x.txt', 'w')",
    "open append keyword": "open('x.txt', mode='a')",
    "open exclusive": "open('x.txt', 'x')",
    "open read-write": "open('x.txt', 'r+')",
    "open non-constant mode": "m = 'w'\nopen('x.txt', mode=m)",
    "Path.write_text": "from pathlib import Path\nPath('a').write_text('x')",
    "Path.write_bytes": "from pathlib import Path\nPath('a').write_bytes(b'x')",
    "Path.open write": "from pathlib import Path\nPath('a').open('w')",
    "os.system": "import os\nos.system('ls')",
    "os.popen": "import os\nos.popen('ls')",
    "eval": "eval('1+1')",
    "exec": "exec('x=1')",
    "random.random": "import random\nx = random.random()",
    "random.seed": "import random\nrandom.seed(1)",
    "random alias": "import random as r\nr.choice([1])",
    "from random import randint": "from random import randint",
    "random.SystemRandom": "import random\nrandom.SystemRandom()",
    "print to stdout": "print('hi')",
    "print to other file": "print('hi', file=out)",
    "sys.stdout.write": "import sys\nsys.stdout.write('x')",
    # review fixes (a): aliases and from-imports
    "import os as o; o.system": "import os as o\no.system('x')",
    "import os as o; o.remove": "import os as o\no.remove('x')",
    "from os import system as s": "from os import system as s\ns('x')",
    "from sys import stdout": "from sys import stdout",
    "import sys as s; s.stdout.write": "import sys as s\ns.stdout.write('x')",
    "sys.__stdout__": "import sys\nsys.__stdout__.write('x')",
    "print file=s.stdout": "import sys as s\nprint('x', file=s.stdout)",
    # (b) positional non-literal mode
    "open positional non-constant mode": "m = 'w'\nopen('x.txt', m)",
    "open positional param mode": "def f(m):\n    return open('x', m)",
    "io.open write": "import io\nio.open('x', 'w')",
    # (c) file mutation
    "shutil import": "import shutil",
    "from shutil import copy": "from shutil import copy",
    "Path.mkdir": "from pathlib import Path\nPath('d').mkdir()",
    "Path.touch": "from pathlib import Path\nPath('d').touch()",
    "Path.unlink": "from pathlib import Path\nPath('d').unlink()",
    "Path.rename": "from pathlib import Path\nPath('d').rename('e')",
    "Path.rmdir": "from pathlib import Path\nPath('d').rmdir()",
    "Path.symlink_to": "from pathlib import Path\nPath('d').symlink_to('e')",
    "logging.FileHandler": "import logging\nlogging.FileHandler('x.log')",
    "logging.basicConfig filename": "import logging\nlogging.basicConfig(filename='x.log')",
    "logging RotatingFileHandler": "import logging.handlers\nlogging.handlers.RotatingFileHandler('x')",
    "fileinput inplace": "import fileinput\nfileinput.input('x', inplace=True)",
    "zipfile write": "import zipfile\nzipfile.ZipFile('a.zip', 'w')",
    "tarfile write": "import tarfile\ntarfile.open('a.tar', 'w')",
    "numpy.save": "import numpy as np\nnp.save('a', [1])",
    "numpy.savetxt": "import numpy as np\nnp.savetxt('a', [1])",
    "pandas to_csv": "df.to_csv('a.csv')",
    "pandas to_json": "df.to_json('a.json')",
    # (d) network capable
    "asyncio.open_connection": "import asyncio\nasyncio.open_connection('h', 1)",
    "asyncio.start_server": "import asyncio\nasyncio.start_server(f, 'h', 1)",
    "loop.create_server": "loop.create_server(f)",
    "loop.create_connection": "loop.create_connection(f)",
    "from asyncio import start_server": "from asyncio import start_server",
    "socketserver": "import socketserver",
    "selectors": "import selectors",
    "poplib": "import poplib",
    "imaplib": "import imaplib",
    "nntplib": "import nntplib",
    "wsgiref": "import wsgiref.simple_server",
    "multiprocessing.connection": "import multiprocessing.connection",
    "from multiprocessing import connection": "from multiprocessing import connection",
    "webbrowser": "import webbrowser",
    "import http": "import http",
    "from http import HTTPStatus": "from http import HTTPStatus",
    "asyncore": "import asyncore",
    "asynchat": "import asynchat",
    "xmlrpc.server": "import xmlrpc.server",
    # (e) dynamic tricks
    "__import__": "__import__('socket')",
    "importlib.import_module": "import importlib\nimportlib.import_module('socket')",
    "importlib.__import__": "import importlib\nimportlib.__import__('socket')",
    "from importlib import import_module": "from importlib import import_module",
    "getattr builtins module": "import builtins\ngetattr(builtins, 'eval')",
    "getattr __builtins__": "getattr(__builtins__, 'eval')",
    "__builtins__ subscript": "__builtins__['eval']('1')",
    "compile": "compile('1', 'f', 'eval')",
    "alias e = exec": "e = exec\ne('x=1')",
    "alias e = eval": "e = eval\ne('1')",
    "builtins.eval": "import builtins\nbuiltins.eval('1')",
    "builtins alias exec": "import builtins as b\nb.exec('x=1')",
    "ctypes": "import ctypes",
    "pty": "import pty",
    "marshal": "import marshal",
    "mmap": "import mmap",
    "runpy": "import runpy",
    "code": "import code",
    "codeop": "import codeop",
    "imp": "import imp",
    # integration review L6
    "io.FileIO": "import io\nio.FileIO('a', 'w')",
    "from io import FileIO": "from io import FileIO\nFileIO('a', 'w')",
    "io alias FileIO": "import io as i\ni.FileIO('a')",
    "os.fdopen": "import os\nos.fdopen(1, 'w')",
    "from os import fdopen": "from os import fdopen",
    "asyncio.create_subprocess_exec": "import asyncio\nasyncio.create_subprocess_exec('ls')",
    "asyncio.create_subprocess_shell": "import asyncio\nasyncio.create_subprocess_shell('ls')",
    "asyncio alias subprocess": "import asyncio as a\na.create_subprocess_exec('ls')",
    "from asyncio import create_subprocess_shell": "from asyncio import create_subprocess_shell as c\nc('ls')",
    "import multiprocessing": "import multiprocessing",
    "from multiprocessing import Pool": "from multiprocessing import Pool",
    "multiprocessing alias": "import multiprocessing as mp",
    "sys.stdout assignment": "import sys\nsys.stdout = open_thing",
    "sys.stderr assignment": "import sys\nsys.stderr = other",
    "sys alias stdout assignment": "import sys as s\ns.stdout = other",
    "from sys import stdout rebinding": "from sys import stdout\nstdout = other",
    "Path.replace one argument": "from pathlib import Path\nPath('a').replace('b')",
    "Path.replace variable": "p.replace(target)",
    "Path.rename call": "p.rename(target)",
    "Path.touch call": "p.touch()",
    "Path.mkdir call": "p.mkdir(parents=True)",
    "os.execv": "import os\nos.execv('a', [])",
    "os.spawnl": "import os\nos.spawnl(0, 'a')",
}
for _name in ("system", "popen", "remove", "unlink", "rename", "replace", "mkdir", "makedirs",
              "write", "open", "truncate", "symlink", "rmdir", "removedirs", "chmod", "chown"):
    BAD_SNIPPETS["from os import " + _name] = "from os import " + _name
    BAD_SNIPPETS["os." + _name] = "import os\nos.%s('a')" % _name

CLEAN_SNIPPET = '''
"""Docstring mentioning socket, subprocess, open('x', 'w') and print('x') is fine."""
import random
import sys
import os.path
from random import Random
# import socket
rng = random.Random(7)
other = Random(3)
with open("data.txt") as fh:
    fh.read()
with open("data.txt", "rb") as fh:
    fh.read()
print("diagnostic", file=sys.stderr)
sys.stderr.write("x")
'''

CLEAN_SNIPPET_2 = '''
import copy
import json
import math
import os
import os.path
import statistics
import sys as s
import time
import random as r
from typing import Any
from random import Random

limit = int(os.environ.get("LIMIT", "3"))
time.sleep(0)
rng = r.Random(5)
data = json.loads(json.dumps(copy.deepcopy({"a": math.sqrt(4), "b": statistics.mean([1, 2])})))
name = os.path.join("a", "b").replace("a", "c")
s.stderr.write("hint")
print("x", file=s.stderr)
def f(x: Any) -> Any:
    return getattr(x, "name", None)
'''

CLEAN_SNIPPET_3 = '''
import io
import logging
import sys
import asyncio
from io import StringIO
logging.disable(logging.CRITICAL + 1)
for h in list(logging.getLogger().handlers):
    logging.getLogger().removeHandler(h)
buf = io.StringIO()
buf2 = StringIO()
text = "a-b".replace("-", "_").replace("_", " ", 1)
stream = sys.stderr
sys.stderr.write("x")
async def f():
    await asyncio.sleep(0)
'''


class TestCheckerSelfTest:
    def test_clean_snippet_three_passes(self):
        assert scan_source(CLEAN_SNIPPET_3) == []

    @pytest.mark.parametrize("label", sorted(BAD_SNIPPETS))
    def test_bad_snippet_is_flagged(self, label):
        assert scan_source(BAD_SNIPPETS[label]), "checker failed to flag: %s" % label

    def test_clean_snippet_passes(self):
        assert scan_source(CLEAN_SNIPPET) == []

    def test_clean_snippet_with_allowed_stdlib_passes(self):
        assert scan_source(CLEAN_SNIPPET_2) == []

    def test_docstrings_and_comments_do_not_trigger(self):
        assert scan_source('"""import socket; eval(1)"""\n# subprocess.run()\nx = 1\n') == []


class TestRealPackage:
    def test_package_override_is_explicitly_allowed(self):
        if PKG_DIR != os.path.abspath(DEFAULT_PKG_DIR):
            assert os.environ.get("BUTTERFLY_ALLOW_OVERRIDE") == "1", (
                "BUTTERFLY_PRIVACY_PKG_DIR=%s differs from this repository (%s); set "
                "BUTTERFLY_ALLOW_OVERRIDE=1 only for scratch-copy mutation checks" % (PKG_DIR, DEFAULT_PKG_DIR))

    def test_package_files_found(self):
        names = [os.path.basename(p) for p in package_sources()]
        assert "server.py" in names and "engine.py" in names, "package scan found: %s" % names

    def test_no_forbidden_patterns_in_package(self):
        violations = []
        for path in package_sources():
            with open(path, "r", encoding="utf-8") as fh:
                violations += scan_source(fh.read(), os.path.relpath(path, ROOT))
        assert not violations, "privacy/determinism violations in %s:\n%s" % (PKG_DIR, "\n".join(violations))
