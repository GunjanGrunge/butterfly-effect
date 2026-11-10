import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp"))

import pytest

from butterfly_mcp.schema import ValidationError
from butterfly_mcp.testmatrix import boundary_values, generate_test_matrix, pairwise


def num(name="n", lo=0, hi=100):
    return {"name": name, "type": "number", "min": lo, "max": hi}


def enum(name, values):
    return {"name": name, "type": "enum", "values": values}


def spec(strategy, params, **extra):
    d = {"target": "t", "parameters": params, "strategy": strategy}
    d.update(extra)
    return d


def sized(n_values_list):
    return [enum(f"p{i}", [f"v{j}" for j in range(n)]) for i, n in enumerate(n_values_list)]


def all_pairs(params, cases):
    covered = set()
    for c in cases:
        for a, b in itertools.combinations([p["name"] for p in params], 2):
            covered.add((a, c[a], b, c[b]))
    return covered


def required_pairs(params):
    req = set()
    for pa, pb in itertools.combinations(params, 2):
        for va in pa["values"]:
            for vb in pb["values"]:
                req.add((pa["name"], va, pb["name"], vb))
    return req


def test_boundary_values_min0_max100():
    vals = boundary_values(num(lo=0, hi=100))
    for v in (-1, 0, 1, 99, 100, 101):
        assert v in vals


def test_boundary_values_dedup_when_narrow():
    vals = boundary_values(num(lo=0, hi=1))
    assert len(vals) == len(set(vals))
    assert 0 in vals and 1 in vals


def test_boundary_values_enum_returns_values():
    assert boundary_values(enum("e", ["a", "b"])) == ["a", "b"]


def test_boundary_strategy_cases_cover_boundaries():
    r = generate_test_matrix(spec("boundary", [num("a"), enum("e", ["x", "y"])]))
    assert r["strategy"] == "boundary"
    assert r["count"] == len(r["cases"])
    assert {-1, 0, 1, 99, 100, 101} <= {c["a"] for c in r["cases"]}
    assert {"x", "y"} <= {c["e"] for c in r["cases"]}
    assert all(set(c) == {"a", "e"} for c in r["cases"])


def test_equivalence_covers_every_enum_value():
    params = [enum("coupon", ["none", "valid", "expired", "malformed"]),
              enum("tier", ["guest", "member", "staff"]), num("total", 0, 1000)]
    r = generate_test_matrix(spec("equivalence", params))
    for p in params[:2]:
        assert {c[p["name"]] for c in r["cases"]} == set(p["values"])
    totals = {c["total"] for c in r["cases"]}
    assert 0 in totals and 1000 in totals
    assert any(0 < t < 1000 for t in totals)


def test_pairwise_covers_all_pairs_and_beats_product():
    params = sized([4, 3, 3])
    cases = pairwise(params)
    assert len(cases) < 36
    assert required_pairs(params) <= all_pairs(params, cases)


def test_pairwise_deterministic():
    params = sized([4, 3, 3, 2])
    assert pairwise(params) == pairwise(params)
    s = spec("pairwise", params)
    assert generate_test_matrix(s) == generate_test_matrix(s)


def test_pairwise_single_parameter():
    cases = pairwise(sized([3]))
    assert [c["p0"] for c in cases] == ["v0", "v1", "v2"]


def test_pairwise_with_number_param_uses_min_mid_max():
    params = [num("n", 0, 10), enum("e", ["a", "b"])]
    r = generate_test_matrix(spec("pairwise", params))
    pairs = {(c["n"], c["e"]) for c in r["cases"]}
    assert pairs == {(n, e) for n in (0, 5, 10) for e in ("a", "b")}
    assert any("pairwise" in n for n in r["notes"])


def test_random_same_seed_identical():
    s = spec("random", [num("a"), enum("e", ["x", "y", "z"])], seed=7)
    assert generate_test_matrix(s) == generate_test_matrix(s)


def test_random_different_seed_differs_and_in_range():
    a = generate_test_matrix(spec("random", [num("a", 0, 10**6)], seed=1))
    b = generate_test_matrix(spec("random", [num("a", 0, 10**6)], seed=2))
    assert a["cases"] != b["cases"]
    assert all(0 <= c["a"] <= 10**6 for c in a["cases"])
    assert a["seed"] == 1


def test_random_does_not_touch_global_random_state():
    import random
    random.seed(123)
    expected = random.random()
    random.seed(123)
    generate_test_matrix(spec("random", [num("a")], seed=5))
    assert random.random() == expected


def test_random_float_range():
    r = generate_test_matrix(spec("random", [num("a", 0.5, 1.5)]))
    assert all(0.5 <= c["a"] <= 1.5 for c in r["cases"])


def test_random_count_option_and_default_seed():
    r = generate_test_matrix(spec("random", [num("a")], count=5))
    assert r["count"] == 5 and len(r["cases"]) == 5
    assert r["seed"] == 42


def test_random_bad_count_rejected():
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("random", [num("a")], count=0))
    assert e.value.field == "count"


def test_invalid_spec_names_field():
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("pairwise", [num("a"), enum("e", [])]))
    assert e.value.field == "parameters[1].values"


def test_unknown_strategy_names_field():
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("nope", [num("a")]))
    assert e.value.field == "strategy"


def test_notes_say_strategy_and_size():
    r = generate_test_matrix(spec("pairwise", sized([10, 10, 10, 10])))
    text = " ".join(r["notes"])
    assert "pairwise" in text
    assert "too large" in text
    small = generate_test_matrix(spec("pairwise", sized([2, 2])))
    assert "too large" not in " ".join(small["notes"])


def test_result_shape_and_input_not_mutated():
    s = spec("equivalence", [enum("e", ["a", "b"])])
    import copy
    before = copy.deepcopy(s)
    r = generate_test_matrix(s)
    assert set(r) == {"strategy", "seed", "count", "cases", "notes"}
    assert s == before


def test_pairwise_large_space_construction_path_covers_all_pairs():
    params = sized([10, 10, 10, 10])
    cases = pairwise(params)
    assert len(cases) < 10000
    assert required_pairs(params) <= all_pairs(params, cases)
    assert cases == pairwise(params)


def test_pairwise_very_large_spec_is_fast_and_complete():
    import time
    params = sized([200, 30])
    t = time.time()
    cases = pairwise(params)
    assert time.time() - t < 5
    assert required_pairs(params) <= all_pairs(params, cases)
    assert len(cases) == 6000


def test_boundary_step_integer_range():
    p = num(lo=0, hi=100)
    assert boundary_values(p) == [-1, 0, 1, 99, 100, 101]
    r = generate_test_matrix(spec("boundary", [p]))
    assert any("step 1" in n for n in r["notes"])


def test_boundary_step_narrow_float_range():
    p = num(lo=0, hi=0.5)
    vals = boundary_values(p)
    assert vals == [-0.05, 0, 0.05, 0.45, 0.5, 0.55]
    assert 0 < vals[2] < 0.5 and 0 < vals[3] < 0.5
    assert vals[0] < 0 and vals[-1] > 0.5
    r = generate_test_matrix(spec("boundary", [p]))
    assert any("step 0.05" in n for n in r["notes"])


def test_boundary_step_float_typed_zero_to_one():
    vals = boundary_values(num(lo=0.0, hi=1.0))
    assert vals == [-0.1, 0.0, 0.1, 0.9, 1.0, 1.1]


def test_boundary_step_min_equals_max():
    assert boundary_values(num(lo=2.5, hi=2.5)) == [1.5, 2.5, 3.5]


def test_random_notes_mention_float_rounding_and_count():
    r = generate_test_matrix(spec("random", [num("a", 0.5, 1.5)]))
    text = " ".join(r["notes"])
    assert "6 decimal places" in text
    assert "count" in text
    ri = generate_test_matrix(spec("random", [num("a", 0, 10)]))
    assert "6 decimal places" not in " ".join(ri["notes"])


PAIR_MSG = "too many value pairs for the pairwise strategy; reduce the parameters or use the random strategy"
MSG = "test matrix time limit exceeded; reduce the parameters or use the random strategy"


def test_time_limit_message_exact_and_pairwise_raises(monkeypatch):
    from butterfly_mcp import testmatrix
    monkeypatch.setattr(testmatrix, "TIME_LIMIT_SECONDS", 0)
    with pytest.raises(ValueError) as e:
        generate_test_matrix(spec("pairwise", sized([30, 30, 30, 30])))
    assert str(e.value) == MSG
    with pytest.raises(ValueError) as e:
        pairwise(sized([30, 30, 30, 30]))
    assert str(e.value) == MSG


@pytest.mark.parametrize("strategy", ["boundary", "equivalence"])
def test_time_limit_other_strategies(monkeypatch, strategy):
    from butterfly_mcp import testmatrix
    monkeypatch.setattr(testmatrix, "TIME_LIMIT_SECONDS", 0)
    with pytest.raises(ValueError) as e:
        generate_test_matrix(spec(strategy, sized([50] * 40)))
    assert str(e.value) == MSG


def test_random_unaffected_by_guard_up_to_1000():
    r = generate_test_matrix(spec("random", sized([40] * 30), count=1000))
    assert r["count"] == 1000


def test_normal_pairwise_output_unchanged_by_guard():
    params = sized([4, 3, 3])
    assert pairwise(params) == pairwise(params)
    assert len(pairwise(params)) < 36


def test_30_by_40_rejected_by_pair_cap():
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("pairwise", sized([40] * 30)))
    assert e.value.field == "parameters"
    assert str(e.value.message) == PAIR_MSG


def test_time_guard_fires_inside_pair_cap_with_limit_zero(monkeypatch):
    from butterfly_mcp import testmatrix
    monkeypatch.setattr(testmatrix, "TIME_LIMIT_SECONDS", 0)
    with pytest.raises(ValueError) as e:
        generate_test_matrix(spec("pairwise", sized([200, 200, 5])))
    assert str(e.value) == MSG


def test_time_guard_checked_inside_pair_building(monkeypatch):
    # one huge row-pair under the cap: the clock must be read many times while building
    from butterfly_mcp import testmatrix
    calls = []
    real = testmatrix.time.monotonic
    monkeypatch.setattr(testmatrix.time, "monotonic", lambda: calls.append(1) or real())
    pairwise(sized([200, 200]))
    assert len(calls) > 50


def test_too_many_parameters_rejected():
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("random", sized([2] * 51)))
    assert e.value.field == "parameters"


def test_too_many_enum_values_rejected():
    params = [enum("a", ["x"]), enum("b", list(range(10001)))]
    with pytest.raises(ValidationError) as e:
        generate_test_matrix(spec("random", params))
    assert e.value.field == "parameters[1].values"


def test_max_sizes_accepted():
    generate_test_matrix(spec("random", sized([2] * 50)))
    generate_test_matrix(spec("random", [enum("b", list(range(10000)))]))


@pytest.fixture
def raw(monkeypatch):
    """Bypass the schema's own length limits so these tests prove the guard on its own."""
    import copy
    from butterfly_mcp import testmatrix

    def passthrough(s):
        out = copy.deepcopy(s)
        if out.get("seed") is None:
            out["seed"] = 42
        return out
    monkeypatch.setattr(testmatrix, "validate_test_scenario", passthrough)


def _peak_and_time(fn):
    import time
    import tracemalloc
    tracemalloc.start()
    t = time.monotonic()
    try:
        out = fn()
        exc = None
    except Exception as e:  # noqa: BLE001
        out, exc = None, e
    elapsed = time.monotonic() - t
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return out, exc, elapsed, peak


@pytest.mark.parametrize("sizes", [[3000, 3000], [10000] * 3, [200] * 50])
def test_pair_cap_rejects_quickly_with_small_memory(sizes):
    params = sized(sizes)
    s = spec("pairwise", params)
    _, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(s))
    assert isinstance(exc, ValidationError)
    assert exc.field == "parameters" and exc.message == PAIR_MSG
    assert elapsed < 3
    assert peak < 150 * 10**6  # includes the validator's copy of the input


def test_just_under_pair_cap_works_and_covers_all_pairs(monkeypatch):
    from butterfly_mcp import testmatrix
    monkeypatch.setattr(testmatrix, "TIME_LIMIT_SECONDS", 120)  # tracemalloc slows things
    params = sized([300, 300])  # 90000 pairs; MAX_OUTPUT_CHARS binds before MAX_PAIRS for 2 params
    assert 300 * 300 <= testmatrix.MAX_PAIRS
    cases, exc, elapsed, peak = _peak_and_time(lambda: pairwise(params))
    assert exc is None
    assert len(cases) == 90000
    seen = {(c["p0"], c["p1"]) for c in cases}
    assert len(seen) == 90000
    print("under-cap peak MB", peak / 1e6, "s", elapsed)
    assert peak < 400 * 10**6


def test_500_by_40_still_fast():
    cases, exc, elapsed, _ = _peak_and_time(lambda: pairwise(sized([500, 40])))
    assert exc is None and len(cases) == 20000 and elapsed < 3


def test_pair_count_uses_number_class_count():
    # numbers contribute 3 classes (min, mid, max): 3 numbers x 3 = 27 pairs, trivially fine
    r = generate_test_matrix(spec("pairwise", [num("a"), num("b"), num("c")]))
    assert 9 <= r["count"] < 27


def test_boundary_largest_request_rejected_small_memory():
    s = spec("boundary", sized([10000] * 50))
    _, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(s))
    assert isinstance(exc, ValidationError) and exc.field == "parameters"
    assert elapsed < 3 and peak < 150 * 10**6


def test_boundary_duplicate_enum_values_still_deduped():
    r = generate_test_matrix(spec("boundary", [enum("e", ["a", "b", "a", "b"])]))
    assert [c["e"] for c in r["cases"]] == ["a", "b"]


def test_equivalence_and_random_largest_request_memory(raw):
    # second-line-of-defense test (schema bypassed by `raw`)
    s = sized([10000] * 50)
    r, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(spec("equivalence", s)))
    assert isinstance(exc, ValidationError) and exc.message == OUT_MSG and peak < 100 * 10**6
    s4 = sized([4000] * 50)
    r, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(spec("equivalence", s4)))
    assert exc is None and r["count"] == 4000 and peak < 200 * 10**6
    print("equivalence peak MB", peak / 1e6, "s", elapsed)
    r, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(spec("random", s)))
    assert exc is None and peak < 200 * 10**6


# ---- round 3: output-size bound, number range guard, duplicates, single-value params ----

OUT_MSG = "result too large; reduce the parameters or use the random strategy"
RANGE_MSG = "number range too large"


def _rejected(s):
    _, exc, elapsed, peak = _peak_and_time(lambda: generate_test_matrix(s))
    assert isinstance(exc, ValidationError), exc
    assert exc.field == "parameters" and exc.message == OUT_MSG
    assert elapsed < 2.5
    assert peak < 100 * 10**6


def test_output_cap_random_long_names(raw):
    params = [enum(f"{i}" + "x" * 1999, ["a"]) for i in range(50)]
    _rejected(spec("random", params, count=1000))


def test_output_cap_boundary_huge_first_value(raw):
    params = [enum(f"p{i}", ["T" * 100000] + [f"v{j}" for j in range(1, 10000)])
              for i in range(9)]
    _rejected(spec("boundary", params))


def test_output_cap_equivalence_long_names(raw):
    params = [enum(f"{i}" + "n" * 10000, [f"v{j}" for j in range(10000)]) for i in range(50)]
    _rejected(spec("equivalence", params))


def test_output_cap_pairwise_long_values(raw):
    params = [enum(f"p{i}", [f"{j}" + "t" * 2000 for j in range(500)]) for i in range(2)]
    _rejected(spec("pairwise", params))


def test_estimate_close_to_real_json_size_and_cap_edge(raw):
    import json
    from butterfly_mcp import testmatrix

    def build(v):
        return spec("random", [enum("p", ["a" * v])], count=1000)

    r = generate_test_matrix(build(4800))
    actual = len(json.dumps(r["cases"]))
    est = testmatrix._size_random([enum("p", ["a" * 4800])], 1000)
    assert actual <= est <= actual * 1.02
    assert est < testmatrix.MAX_OUTPUT_CHARS
    _rejected(build(5100))

    params = [enum("p", [f"v{j}" for j in range(37)]), enum("q", ["x", "yy", "zzz"])]
    r = generate_test_matrix(spec("equivalence", params))
    classes = [p["values"] for p in params]
    est = testmatrix._size_equivalence(params, classes)
    actual = len(json.dumps(r["cases"]))
    assert actual <= est <= actual * 1.15


@pytest.mark.parametrize("strategy", ["boundary", "equivalence", "pairwise", "random"])
def test_number_range_too_large(strategy, raw):
    for lo, hi in ((-1e308, 1e308), (0, 1.7e308)):
        with pytest.raises(ValidationError) as e:
            generate_test_matrix(spec(strategy, [enum("a", ["x"]), num("n", lo, hi)]))
        assert e.value.field == "parameters[1]" and e.value.message == RANGE_MSG


def test_results_never_contain_inf_or_nan():
    import json
    params = [num("n", 0.5, 1.5), num("m", -1e12, 1e12), enum("e", ["a", "b"])]
    for strategy in ("boundary", "equivalence", "pairwise", "random"):
        r = generate_test_matrix(spec(strategy, params))
        json.dumps(r, allow_nan=False)


def test_duplicate_enum_values_removed_with_note():
    vals = [f"v{i}" for i in range(500)]
    for strategy in ("equivalence", "pairwise", "boundary"):
        plain = generate_test_matrix(spec(strategy, [enum("a", vals), enum("b", ["x", "y"])]))
        dup = generate_test_matrix(
            spec(strategy, [enum("a", vals + vals), enum("b", ["x", "y", "x"])]))
        assert dup["cases"] == plain["cases"]
        assert any("duplicate" in n.lower() for n in dup["notes"])
        assert not any("duplicate" in n.lower() for n in plain["notes"])


def test_duplicates_compare_by_type_and_unhashable_by_json(raw):
    r = generate_test_matrix(spec("equivalence", [enum("a", [1, True, 1.0, "1", 1, [1], [1]])]))
    got = [c["a"] for c in r["cases"]]
    assert len(got) == 5
    assert got[0] == 1 and got[1] is True and isinstance(got[2], float)
    assert got[3] == "1" and got[4] == [1]


def test_pairwise_single_value_parameters_fast_and_covered():
    import time
    params = [enum("big", [f"v{i}" for i in range(2000)])] + \
        [enum(f"s{i}", [f"only{i}"]) for i in range(49)]
    t = time.monotonic()
    cases = pairwise(params)
    assert time.monotonic() - t < 3
    assert required_pairs(params[:1] + params[1:3]) <= all_pairs(params[:3], cases)
    assert {c["big"] for c in cases} == {f"v{i}" for i in range(2000)}
    assert all(c[f"s{i}"] == f"only{i}" for c in cases for i in range(49))
    assert all(list(c) == [p["name"] for p in params] for c in cases)


def test_pairwise_singles_mixed_in_middle_full_coverage():
    params = [enum("a", ["a1", "a2", "a3"]), enum("s", ["only"]),
              enum("b", ["b1", "b2"]), enum("c", ["c1", "c2", "c3"])]
    cases = pairwise(params)
    assert required_pairs(params) <= all_pairs(params, cases)
    assert pairwise(params) == cases
    assert pairwise([enum("s", ["only"]), enum("t", ["x"])]) == [{"s": "only", "t": "x"}]


def test_schema_valid_worst_case_is_rejected_by_output_cap():
    # end to end with the real schema: 50 parameters, 100-char names, 200-char values
    params = [enum(f"{i:02d}" + "n" * 98, ["v" * 200]) for i in range(50)]
    _rejected(spec("random", params, count=1000))


def test_schema_valid_moderate_random_accepted():
    import json
    params = [enum(f"{i:02d}" + "n" * 98, ["v" * 100]) for i in range(10)]
    r = generate_test_matrix(spec("random", params, count=1000))
    assert len(json.dumps(r)) < 5000000
