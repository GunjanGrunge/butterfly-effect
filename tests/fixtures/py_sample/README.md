# py_sample

Tiny invented discount calculator (`discount.calculate_discount`) with existing tests in
`tests/test_discount_basic.py` and `tests/test_discount_invalid_totals.py`.
Run them from this folder (or from a copy) with: `python -m pytest -q`

Collection note: inside the Butterfly Effect repository (this folder at `tests/fixtures/py_sample`)
the fixture's own tests are NOT collected by the repository's test run, unless
`BUTTERFLY_RUN_FIXTURE_TESTS=1` is set. A copy placed anywhere else runs normally.
Limitation: the rule is decided by the path alone, so any copy whose path ends in
`/tests/fixtures/py_sample` is also skipped (set the variable to run it).
