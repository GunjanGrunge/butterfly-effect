import copy
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp"))

import pytest

from butterfly_mcp.engine import compare_options, run_simulation
from butterfly_mcp.schema import ValidationError


def base(**over):
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
        "runs": 500,
        "seed": 7,
    }
    s.update(over)
    return s


def test_reproducible():
    s = base(dynamic_events=[
        {"name": "medical", "monthly_probability": 0.1, "amount": {"low": 1000, "high": 90000}},
        {"name": "dip", "monthly_probability": 0.1, "income_drop_pct": 40, "duration_months": 3},
    ])
    assert compare_options(copy.deepcopy(s)) == compare_options(copy.deepcopy(s))
    assert run_simulation(copy.deepcopy(s), "Car") == run_simulation(copy.deepcopy(s), "Car")


def test_hand_computed_end_balance():
    s = base(typical_expenses={"monthly": 45000})  # costs 25000+45000 = 70000
    r = run_simulation(s, "Zero")
    assert r["end_balance"] == {"p10": 360000, "p50": 360000, "p90": 360000}
    assert r["confidence_pct"] == 100.0
    assert r["criterion_met_runs"] == r["runs"] == 500


def test_option_cost_and_upfront_hand_computed():
    s = base(savings=50000)
    s["options"] = [{"name": "X", "monthly_cost": 10000, "upfront": 20000, "duration_months": 6}]
    r = run_simulation(s, "X")
    # 50000 - 20000 + 12*30000 - 6*10000 = 330000
    assert r["end_balance"]["p50"] == 330000
    assert r["worst_month_balance"] == 30000


def test_event_probability_zero_and_one():
    ev = lambda p: [{"name": "medical", "monthly_probability": p, "amount": {"low": 500000, "high": 500000}}]
    never = run_simulation(base(dynamic_events=ev(0)), "Zero")
    assert never["confidence_pct"] == 100.0
    assert "medical" not in never["top_failure_causes"]
    always = run_simulation(base(dynamic_events=ev(1)), "Zero")
    assert always["confidence_pct"] == 0.0
    assert always["top_failure_causes"][0] == "medical"


def test_confidence_monotone_in_cost():
    ev = [{"name": "medical", "monthly_probability": 0.1, "amount": {"low": 1000, "high": 120000}}]
    prev = 101.0
    for cost in (0, 10000, 20000, 30000, 40000):
        s = base(dynamic_events=ev, savings=20000)
        s["options"] = [{"name": "O", "monthly_cost": cost, "upfront": 0, "duration_months": 12}]
        c = run_simulation(s, "O")["confidence_pct"]
        assert c <= prev
        prev = c


def test_zero_cost_option_solvent_is_100():
    assert run_simulation(base(), "Zero")["confidence_pct"] == 100.0


def test_infeasible_option_is_zero():
    s = base(savings=1000)
    s["options"] = [{"name": "Big", "monthly_cost": 0, "upfront": 5000, "duration_months": 0}]
    r = run_simulation(s, "Big")
    assert r["confidence_pct"] == 0.0
    assert r["criterion_met_runs"] == 0
    assert r["worst_month_balance"] == -4000


def test_income_drop_event_applies_for_duration():
    s = base(dynamic_events=[
        {"name": "dip", "monthly_probability": 1, "income_drop_pct": 100, "duration_months": 3}])
    r = run_simulation(s, "Zero")
    assert r["confidence_pct"] == 0.0
    assert r["top_failure_causes"][0] == "dip"


def test_compare_shape_and_recommendation():
    s = base(dynamic_events=[
        {"name": "medical", "monthly_probability": 0.05, "amount": {"low": 1000, "high": 90000}}])
    s["savings"] = 10000
    out = compare_options(s)
    assert out["method"] == "monte_carlo" and out["seed"] == 7
    assert [o["name"] for o in out["options"]] == ["Zero", "Car"]
    best = max(out["options"], key=lambda o: o["confidence_pct"])
    assert out["recommended"] == best["name"]
    assert any("tie" in a.lower() for a in out["assumptions"])
    assert out["sensitivity"]
    for row in out["sensitivity"]:
        assert set(row) == {"assumption", "change", "confidence_delta_pct"}


def test_tie_broken_by_median_end_balance():
    s = base()
    s["options"] = [
        {"name": "A", "monthly_cost": 10000, "upfront": 0, "duration_months": 12},
        {"name": "B", "monthly_cost": 0, "upfront": 0, "duration_months": 0},
    ]
    out = compare_options(s)  # both 100%
    assert out["recommended"] == "B"


def test_unknown_option_and_invalid_scenario():
    with pytest.raises(ValueError):
        run_simulation(base(), "Nope")
    with pytest.raises(ValidationError):
        run_simulation({"currency": "x"}, "Zero")


def test_time_guard(monkeypatch):
    import butterfly_mcp.engine as e
    monkeypatch.setattr(e, "TIME_LIMIT_SECONDS", 0)
    with pytest.raises(ValueError, match="simulation time limit exceeded; reduce runs"):
        run_simulation(base(), "Zero")


def test_performance_10k_runs_60_months():
    s = base(horizon_months=60, runs=10000, dynamic_events=[
        {"name": "medical", "monthly_probability": 0.02, "amount": {"low": 10000, "high": 150000}},
        {"name": "dip", "monthly_probability": 0.03, "income_drop_pct": 30, "duration_months": 3}])
    s["income"] = {"monthly": 100000, "variability_pct": 5}
    t = time.perf_counter()
    run_simulation(s, "Car")
    dt = time.perf_counter() - t
    print(f"\n10000 runs x 60 months: {dt:.2f}s")
    assert dt < 5


# ---- review-fix tests ----

class _Scripted:
    """Stand-in for random.Random that fires chosen (month, event_index) pairs.

    The engine draws, per month and per event in order, rand() then uniform();
    any further uniform() call (income variability) is not used in these tests.
    """
    schedule = set()
    n_events = 1

    def __init__(self, seed):
        self.calls = 0

    def random(self):
        c = self.calls
        self.calls += 1
        month, idx = divmod(c, self.n_events)
        return 0.0 if (month + 1, idx) in self.schedule else 1.0

    def uniform(self, a, b):
        return (a + b) / 2


def _scripted(monkeypatch, schedule, n_events):
    import butterfly_mcp.engine as e
    cls = type("S", (_Scripted,), {"schedule": set(schedule), "n_events": n_events})
    monkeypatch.setattr(e.random, "Random", cls)


def _flat(events, horizon):
    return {
        "currency": "INR", "horizon_months": horizon, "income": {"monthly": 100},
        "savings": 0,
        "options": [{"name": "Z", "monthly_cost": 0, "upfront": 0, "duration_months": 0}],
        "dynamic_events": events,
        "success_criterion": {"type": "never_below", "balance": -10**9},
        "runs": 1, "seed": 1,
    }


def test_drop_duration_single_event_exact(monkeypatch):
    # Fires only in month 1: 100% drop for 2 months -> incomes 0, 0, 100, 100.
    _scripted(monkeypatch, {(1, 0)}, 1)
    s = _flat([{"name": "d", "monthly_probability": 0.5, "income_drop_pct": 100,
                "duration_months": 2}], 4)
    assert run_simulation(s, "Z")["end_balance"]["p50"] == 200


def test_overlapping_drops_use_largest_active_per_month(monkeypatch):
    # A (50%, 4 months) fires month 1, B (10%, 4 months) fires month 3.
    # Months 1-4 at 50%, months 5-6 at 10%: 4*50 + 2*90 = 380.
    _scripted(monkeypatch, {(1, 0), (3, 1)}, 2)
    s = _flat([
        {"name": "A", "monthly_probability": 0.5, "income_drop_pct": 50, "duration_months": 4},
        {"name": "B", "monthly_probability": 0.5, "income_drop_pct": 10, "duration_months": 4},
    ], 6)
    assert run_simulation(s, "Z")["end_balance"]["p50"] == 380


def _no_cost(var):
    s = base(runs=300)
    s["income"] = {"monthly": 100000, "variability_pct": var}
    s["fixed_commitments"] = []
    s["typical_expenses"] = {"monthly": 0}
    return s


def test_income_never_negative_at_max_variability():
    r = run_simulation(_no_cost(100), "Zero")
    assert r["worst_month_balance"] >= 0
    assert r["end_balance"]["p10"] >= 0


def test_clamp_protects_engine_beyond_schema_range():
    import butterfly_mcp.engine as e
    sc = e.validate_scenario(_no_cost(100))
    sc["income"]["variability_pct"] = 300  # bypass the schema after validation
    deadline = time.perf_counter() + 20
    _met, ends, worst, _causes = e._simulate(sc, sc["options"][0], deadline)
    assert worst >= 0 and min(ends) >= 0


def test_variability_above_100_rejected_with_field():
    with pytest.raises(ValidationError) as ei:
        compare_options(_no_cost(150))
    assert ei.value.field == "income.variability_pct"


def test_duplicate_option_names_rejected_before_simulation(monkeypatch):
    import butterfly_mcp.engine as e
    monkeypatch.setattr(e, "_simulate", lambda *a, **k: pytest.fail("simulated"))
    s = base()
    s["options"] = [{"name": "A", "monthly_cost": 0, "upfront": 0, "duration_months": 0},
                    {"name": " a ", "monthly_cost": 0, "upfront": 0, "duration_months": 0}]
    with pytest.raises(ValidationError) as ei:
        compare_options(s)
    assert ei.value.field == "options[1].name"


def test_option_lookup_case_insensitive():
    s = base()
    s["options"] = [{"name": "Buy on EMI", "monthly_cost": 0, "upfront": 0, "duration_months": 0}]
    exact = run_simulation(s, "Buy on EMI")
    assert run_simulation(s, "  buy on emi ")["name"] == "Buy on EMI"
    assert exact["name"] == "Buy on EMI"
    with pytest.raises(ValueError, match="unknown option: nope"):
        run_simulation(s, "nope")


def _risky():
    s = base(savings=0, typical_expenses={"monthly": 45000},
             dynamic_events=[{"name": "shock", "monthly_probability": 0.0,
                              "amount": {"low": 500000, "high": 500000}}])
    s["income"] = {"monthly": 70000}  # exactly breakeven with 25000+45000 costs
    s["fixed_commitments"] = [{"name": "rent", "monthly": 25000}]
    return s


def test_sensitivity_option_and_values():
    s = _risky()
    s["options"] = [{"name": "Zero", "monthly_cost": 0, "upfront": 0, "duration_months": 0}]
    out = compare_options(s)
    assert out["sensitivity_option"] == out["recommended"] == "Zero"
    rows = {r["assumption"]: r for r in out["sensitivity"]}
    # income -5% on a break-even budget: every run fails, 100 -> 0.
    assert rows["monthly income"]["confidence_delta_pct"] == -100.0
    alt = copy.deepcopy(s)
    alt["dynamic_events"][0]["monthly_probability"] = 0.01
    expected = run_simulation(alt, "Zero")["confidence_pct"] - 100.0
    got = rows["shock probability"]["confidence_delta_pct"]
    assert got == round(expected, 2) and got < 0


def test_sensitivity_skips_probability_one_event():
    s = base(dynamic_events=[
        {"name": "sure", "monthly_probability": 1, "amount": {"low": 1, "high": 1}},
        {"name": "maybe", "monthly_probability": 0.1, "amount": {"low": 1, "high": 1}}])
    names = [r["assumption"] for r in compare_options(s)["sensitivity"]]
    assert "sure probability" not in names
    assert "maybe probability" in names


def test_assumptions_document_caveats():
    text = " ".join(compare_options(base())["assumptions"]).lower()
    assert "not proof of robustness" in text
    assert "lowest balance" in text and "any single run" in text
    assert "most recent" in text  # failure-cause attribution rule


def test_tie_break_listed_order():
    for names in (["A", "B"], ["B", "A"]):
        s = base()
        s["options"] = [{"name": n, "monthly_cost": 0, "upfront": 0, "duration_months": 0}
                        for n in names]
        assert compare_options(s)["recommended"] == names[0]
