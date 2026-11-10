import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp"))

import pytest

from butterfly_mcp.schema import (
    DEFAULT_RUNS,
    MAX_HORIZON_MONTHS,
    MAX_RUNS,
    ValidationError,
    validate_scenario,
    validate_test_scenario,
)


def good_scenario():
    return {
        "decision": "Take a car on EMI",
        "currency": "INR",
        "horizon_months": 36,
        "income": {"monthly": 100000, "variability_pct": 0},
        "fixed_commitments": [{"name": "rent", "monthly": 25000}],
        "typical_expenses": {"monthly": 20000},
        "savings": 200000,
        "options": [
            {"name": "Buy on EMI", "monthly_cost": 50000, "upfront": 100000, "duration_months": 60},
            {"name": "Do not buy", "monthly_cost": 0, "upfront": 0, "duration_months": 0},
        ],
        "dynamic_events": [
            {"name": "medical", "monthly_probability": 0.02, "amount": {"low": 10000, "high": 150000}},
            {"name": "income dip", "monthly_probability": 0.03, "income_drop_pct": 30, "duration_months": 3},
        ],
        "success_criterion": {"type": "never_below", "balance": 50000},
    }


def good_test_scenario():
    return {
        "target": "checkout.apply_discount",
        "parameters": [
            {"name": "cart_total", "type": "number", "min": 0, "max": 100000},
            {"name": "coupon", "type": "enum", "values": ["none", "valid", "expired"]},
        ],
        "strategy": "pairwise",
    }


def assert_field(fn, data, field):
    with pytest.raises(ValidationError) as exc:
        fn(data)
    assert exc.value.field == field
    assert exc.value.message


def test_constants():
    assert (DEFAULT_RUNS, MAX_RUNS, MAX_HORIZON_MONTHS) == (10000, 100000, 600)


def test_missing_currency():
    d = good_scenario()
    del d["currency"]
    assert_field(validate_scenario, d, "currency")


def test_negative_income():
    d = good_scenario()
    d["income"]["monthly"] = -1
    assert_field(validate_scenario, d, "income.monthly")


def test_probability_above_one():
    d = good_scenario()
    d["dynamic_events"][0]["monthly_probability"] = 1.2
    assert_field(validate_scenario, d, "dynamic_events[0].monthly_probability")


def test_event_high_below_low():
    d = good_scenario()
    d["dynamic_events"][0]["amount"] = {"low": 100, "high": 50}
    assert_field(validate_scenario, d, "dynamic_events[0].amount.high")


def test_runs_above_max():
    d = good_scenario()
    d["runs"] = 100001
    assert_field(validate_scenario, d, "runs")


def test_horizon_zero():
    d = good_scenario()
    d["horizon_months"] = 0
    assert_field(validate_scenario, d, "horizon_months")


def test_empty_enum():
    d = good_test_scenario()
    d["parameters"][1]["values"] = []
    assert_field(validate_test_scenario, d, "parameters[1].values")


def test_min_above_max():
    d = good_test_scenario()
    d["parameters"][0]["min"] = 10
    d["parameters"][0]["max"] = 5
    assert_field(validate_test_scenario, d, "parameters[0].min")


def test_unknown_strategy():
    d = good_test_scenario()
    d["strategy"] = "magic"
    assert_field(validate_test_scenario, d, "strategy")


def test_valid_scenario_round_trip_with_defaults():
    d = good_scenario()
    original = copy.deepcopy(d)
    out = validate_scenario(d)
    assert d == original  # input not mutated
    assert out["runs"] == DEFAULT_RUNS
    assert out["seed"] == 42
    assert out["currency"] == "INR"
    assert out["options"] == original["options"]
    assert validate_scenario(out) == out


def test_valid_test_scenario_passes():
    out = validate_test_scenario(good_test_scenario())
    assert out["strategy"] == "pairwise"
    assert out["target"] == "checkout.apply_discount"


# ---- integration fixes: M2, L2 and boundary coverage ----

def test_duplicate_option_names_rejected():
    d = good_scenario()
    d["options"][1]["name"] = "Buy on EMI"
    with pytest.raises(ValidationError) as exc:
        validate_scenario(d)
    assert exc.value.field == "options[1].name"
    assert exc.value.message == "must be unique"
    assert "Buy on EMI" not in exc.value.message


def test_duplicate_option_names_ignore_case_and_whitespace():
    d = good_scenario()
    d["options"][0]["name"] = "Buy"
    d["options"][1]["name"] = "  buy "
    assert_field(validate_scenario, d, "options[1].name")


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_option_name_rejected(bad):
    d = good_scenario()
    d["options"][0]["name"] = bad
    assert_field(validate_scenario, d, "options[0].name")


def test_variability_pct_above_100():
    d = good_scenario()
    d["income"]["variability_pct"] = 100.01
    assert_field(validate_scenario, d, "income.variability_pct")


def test_variability_pct_negative():
    d = good_scenario()
    d["income"]["variability_pct"] = -0.01
    assert_field(validate_scenario, d, "income.variability_pct")


@pytest.mark.parametrize("v", [100.01, -0.01])
def test_income_drop_pct_out_of_range(v):
    d = good_scenario()
    d["dynamic_events"][1]["income_drop_pct"] = v
    assert_field(validate_scenario, d, "dynamic_events[1].income_drop_pct")


@pytest.mark.parametrize("v", [0, 100])
def test_percentages_valid_boundaries(v):
    d = good_scenario()
    d["income"]["variability_pct"] = v
    d["dynamic_events"][1]["income_drop_pct"] = v
    out = validate_scenario(d)
    assert out["income"]["variability_pct"] == v


@pytest.mark.parametrize("runs", [1, 100000])
def test_runs_valid_boundaries(runs):
    d = good_scenario()
    d["runs"] = runs
    assert validate_scenario(d)["runs"] == runs


@pytest.mark.parametrize("h", [1, 600])
def test_horizon_valid_boundaries(h):
    d = good_scenario()
    d["horizon_months"] = h
    assert validate_scenario(d)["horizon_months"] == h


@pytest.mark.parametrize("p", [0, 1])
def test_probability_valid_boundaries(p):
    d = good_scenario()
    d["dynamic_events"][0]["monthly_probability"] = p
    assert validate_scenario(d)["dynamic_events"][0]["monthly_probability"] == p


def test_amount_high_equal_low_valid():
    d = good_scenario()
    d["dynamic_events"][0]["amount"] = {"low": 5, "high": 5}
    validate_scenario(d)


def _set_income(d, v):
    d["income"]["monthly"] = v


def _set_savings(d, v):
    d["savings"] = v


def _set_cost(d, v):
    d["options"][0]["monthly_cost"] = v


def _set_amount(d, v):
    d["dynamic_events"][0]["amount"] = {"low": v, "high": v}


@pytest.mark.parametrize("setter,field", [
    (_set_income, "income.monthly"),
    (_set_savings, "savings"),
    (_set_cost, "options[0].monthly_cost"),
    (_set_amount, "dynamic_events[0].amount.low"),
])
@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), float("-inf")])
def test_non_finite_and_bool_rejected(setter, field, bad):
    d = good_scenario()
    setter(d, bad)
    assert_field(validate_scenario, d, field)


# ---- round 3: size bounds for test scenarios ----
from butterfly_mcp.schema import (
    MAX_ENUM_VALUE_LENGTH,
    MAX_NAME_LENGTH,
    MAX_NUMBER_MAGNITUDE,
    MAX_TOTAL_VALUE_CHARS,
)

MARK = "SECRETMARKER"


def _rejects(data, field):
    with pytest.raises(ValidationError) as exc:
        validate_test_scenario(data)
    assert exc.value.field == field
    assert MARK not in exc.value.message
    assert MARK not in str(exc.value)
    return exc.value


def test_size_constants():
    assert MAX_NAME_LENGTH == 100
    assert MAX_ENUM_VALUE_LENGTH == 200
    assert MAX_TOTAL_VALUE_CHARS == 1000000
    assert MAX_NUMBER_MAGNITUDE == 1e15


def test_target_length_boundary():
    d = good_test_scenario()
    d["target"] = "t" * 100
    validate_test_scenario(d)
    d["target"] = MARK + "t" * 100
    _rejects(d, "target")


def test_param_name_length_boundary():
    d = good_test_scenario()
    d["parameters"][1]["name"] = "n" * 100
    validate_test_scenario(d)
    d["parameters"][1]["name"] = MARK + "n" * 100
    _rejects(d, "parameters[1].name")


def test_enum_text_length_boundary():
    d = good_test_scenario()
    d["parameters"][1]["values"] = ["v" * 200]
    validate_test_scenario(d)
    d["parameters"][1]["values"] = ["ok", MARK + "v" * 200]
    _rejects(d, "parameters[1].values[1]")


def test_enum_scalars_still_valid():
    d = good_test_scenario()
    d["parameters"][1]["values"] = ["valid", "guest", 3, 2.5, True, False, None]
    validate_test_scenario(d)


@pytest.mark.parametrize("bad", [["a"], {"k": MARK}, [MARK]])
def test_enum_non_scalar_rejected(bad):
    d = good_test_scenario()
    d["parameters"][1]["values"] = ["ok", bad]
    _rejects(d, "parameters[1].values[1]")


@pytest.mark.parametrize("bad", [10**4000, float("nan"), float("inf")])
def test_enum_big_or_nonfinite_numbers_rejected(bad):
    d = good_test_scenario()
    d["parameters"][1]["values"] = [bad]
    _rejects(d, "parameters[1].values[0]")


def test_total_chars_boundary():
    d = good_test_scenario()
    vals = ["v" * 200] * 4999 + ["w" * 199]
    d["parameters"] = [{"name": "a", "type": "enum", "values": vals}]
    validate_test_scenario(d)  # exactly 1,000,000 characters
    vals[-1] = "w" * 200
    err = _rejects(d, "parameters")
    assert err.message == (
        "request too large: too many characters in names and values; "
        "reduce the parameters or the values"
    )


@pytest.mark.parametrize("v", [1e15, -1e15, 10**15, -(10**15)])
def test_number_magnitude_boundary_valid(v):
    d = good_test_scenario()
    d["parameters"][0].update(min=-1 if v > 0 else v, max=v if v > 0 else 1)
    validate_test_scenario(d)


@pytest.mark.parametrize("bad", [1e15 * 1.0000001, 10**15 + 1, 1e308, 10**4000])
def test_number_magnitude_rejected(bad):
    d = good_test_scenario()
    d["parameters"][0]["max"] = bad
    _rejects(d, "parameters[0].max")
    d = good_test_scenario()
    d["parameters"][0]["min"] = -bad
    _rejects(d, "parameters[0].min")


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf")])
def test_number_param_bad_types_rejected(bad):
    d = good_test_scenario()
    d["parameters"][0]["max"] = bad
    _rejects(d, "parameters[0].max")
