"""Keep this sample project's own tests out of the Butterfly Effect repository's test run.

The tests here are fixtures for behavior scenarios, not part of the plugin suite. They are
skipped only when this folder sits inside the repository's tests/fixtures folder. A copy placed
anywhere else runs them normally. Set BUTTERFLY_RUN_FIXTURE_TESTS=1 to run them in place.
"""
import os

_here = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
_inside_repo_fixtures = _here.endswith("/tests/fixtures/py_sample")

if _inside_repo_fixtures and not os.environ.get("BUTTERFLY_RUN_FIXTURE_TESTS"):
    collect_ignore_glob = ["tests/*", "tests"]
