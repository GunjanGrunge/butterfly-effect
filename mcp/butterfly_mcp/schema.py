"""Validation for Scenario and TestScenario. Pure functions, standard library only."""

import copy
import json

DEFAULT_RUNS = 10000
MAX_RUNS = 100000
MAX_HORIZON_MONTHS = 600
DEFAULT_SEED = 42
MAX_NAME_LENGTH = 100
MAX_ENUM_VALUE_LENGTH = 200
MAX_TOTAL_VALUE_CHARS = 1000000
MAX_NUMBER_MAGNITUDE = 1e15
STRATEGIES = ("boundary", "equivalence", "pairwise", "random")
PARAM_TYPES = ("number", "enum")


class ValidationError(Exception):
    def __init__(self, field, message):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v \
        and v not in (float("inf"), float("-inf"))


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _dict(data, field):
    if not isinstance(data, dict):
        raise ValidationError(field, "must be an object")
    return data


def _require(d, key, path):
    if key not in d or d[key] is None:
        raise ValidationError(path, "is required")
    return d[key]


def _number(d, key, path, minimum=0.0, required=True):
    if key not in d or d[key] is None:
        if required:
            raise ValidationError(path, "is required")
        return None
    v = d[key]
    if not _is_num(v):
        raise ValidationError(path, "must be a number")
    if v < minimum:
        raise ValidationError(path, f"must be at least {minimum:g}")
    return v


def _int_range(d, key, path, lo, hi, required=True):
    if key not in d or d[key] is None:
        if required:
            raise ValidationError(path, "is required")
        return None
    v = d[key]
    if not _is_int(v):
        raise ValidationError(path, "must be an integer")
    if v < lo or v > hi:
        raise ValidationError(path, f"must be between {lo} and {hi}")
    return v


def _name(d, path):
    v = _require(d, "name", path)
    if not isinstance(v, str) or not v.strip():
        raise ValidationError(path, "must be a non-empty string")


def validate_scenario(data):
    d = _dict(data, "scenario")
    out = copy.deepcopy(d)

    cur = _require(d, "currency", "currency")
    if not isinstance(cur, str) or not cur.strip():
        raise ValidationError("currency", "must be a non-empty string")

    _int_range(d, "horizon_months", "horizon_months", 1, MAX_HORIZON_MONTHS)

    income = _dict(_require(d, "income", "income"), "income")
    _number(income, "monthly", "income.monthly")
    var = _number(income, "variability_pct", "income.variability_pct", required=False)
    if var is not None and var > 100:
        raise ValidationError("income.variability_pct", "must be between 0 and 100")

    _number(d, "savings", "savings", minimum=float("-inf"))

    commitments = d.get("fixed_commitments")
    if commitments is not None:
        if not isinstance(commitments, list):
            raise ValidationError("fixed_commitments", "must be a list")
        for i, c in enumerate(commitments):
            p = f"fixed_commitments[{i}]"
            _dict(c, p)
            _name(c, p + ".name")
            _number(c, "monthly", p + ".monthly")

    exp = d.get("typical_expenses")
    if exp is not None:
        _number(_dict(exp, "typical_expenses"), "monthly", "typical_expenses.monthly")

    options = _require(d, "options", "options")
    if not isinstance(options, list) or not options:
        raise ValidationError("options", "must be a non-empty list")
    seen_names = set()
    for i, o in enumerate(options):
        p = f"options[{i}]"
        _dict(o, p)
        _name(o, p + ".name")
        key = o["name"].strip().casefold()
        if key in seen_names:
            raise ValidationError(p + ".name", "must be unique")
        seen_names.add(key)
        _number(o, "monthly_cost", p + ".monthly_cost")
        _number(o, "upfront", p + ".upfront")
        _int_range(o, "duration_months", p + ".duration_months", 0, MAX_HORIZON_MONTHS)

    events = d.get("dynamic_events")
    if events is not None:
        if not isinstance(events, list):
            raise ValidationError("dynamic_events", "must be a list")
        for i, e in enumerate(events):
            p = f"dynamic_events[{i}]"
            _dict(e, p)
            _name(e, p + ".name")
            prob = _number(e, "monthly_probability", p + ".monthly_probability")
            if prob > 1:
                raise ValidationError(p + ".monthly_probability", "must be between 0 and 1")
            if "amount" in e and e["amount"] is not None:
                amt = _dict(e["amount"], p + ".amount")
                low = _number(amt, "low", p + ".amount.low")
                high = _number(amt, "high", p + ".amount.high")
                if high < low:
                    raise ValidationError(p + ".amount.high", "must not be below amount.low")
            if "income_drop_pct" in e and e["income_drop_pct"] is not None:
                drop = _number(e, "income_drop_pct", p + ".income_drop_pct")
                if drop > 100:
                    raise ValidationError(p + ".income_drop_pct", "must be between 0 and 100")
                _int_range(e, "duration_months", p + ".duration_months", 1, MAX_HORIZON_MONTHS)
            if not ("amount" in e and e["amount"] is not None) and \
                    not ("income_drop_pct" in e and e["income_drop_pct"] is not None):
                raise ValidationError(p, "needs amount or income_drop_pct")

    crit = _dict(_require(d, "success_criterion", "success_criterion"), "success_criterion")
    ctype = _require(crit, "type", "success_criterion.type")
    if ctype != "never_below":
        raise ValidationError("success_criterion.type", "must be 'never_below'")
    _number(crit, "balance", "success_criterion.balance", minimum=float("-inf"))

    out["runs"] = _int_range(d, "runs", "runs", 1, MAX_RUNS, required=False) or DEFAULT_RUNS
    seed = d.get("seed")
    if seed is None:
        seed = DEFAULT_SEED
    elif not _is_int(seed):
        raise ValidationError("seed", "must be an integer")
    out["seed"] = seed
    return out


def _short_text(v, path, field_label="must be a non-empty text of at most 100 characters"):
    if not isinstance(v, str) or not v.strip() or len(v) > MAX_NAME_LENGTH:
        raise ValidationError(path, field_label)


def _bounded_number(prm, key, path):
    v = _require(prm, key, path)
    if not _is_num(v) or abs(v) > MAX_NUMBER_MAGNITUDE:
        raise ValidationError(path, "must be a finite number no larger than 1e15 in size")
    return v


def _enum_value_chars(v, path):
    """Return the character cost of one enum value, or raise."""
    msg = "must be text, a number, true/false or null, at most 200 characters"
    if v is None or isinstance(v, bool):
        return len(json.dumps(v))
    if isinstance(v, str):
        if len(v) > MAX_ENUM_VALUE_LENGTH:
            raise ValidationError(path, msg)
        return len(v)
    if _is_num(v):
        if isinstance(v, int) and v.bit_length() > 1000:
            raise ValidationError(path, msg)
        n = len(json.dumps(v))
        if n > MAX_ENUM_VALUE_LENGTH:
            raise ValidationError(path, msg)
        return n
    raise ValidationError(path, msg)


def validate_test_scenario(data):
    d = _dict(data, "test_scenario")
    out = copy.deepcopy(d)

    t = _require(d, "target", "target")
    _short_text(t, "target")

    params = _require(d, "parameters", "parameters")
    if not isinstance(params, list) or not params:
        raise ValidationError("parameters", "must be a non-empty list")
    total_chars = 0
    too_large = ValidationError(
        "parameters",
        "request too large: too many characters in names and values; "
        "reduce the parameters or the values",
    )
    for i, prm in enumerate(params):
        p = f"parameters[{i}]"
        _dict(prm, p)
        _short_text(_require(prm, "name", p + ".name"), p + ".name")
        total_chars += len(prm["name"])
        if total_chars > MAX_TOTAL_VALUE_CHARS:
            raise too_large
        ptype = _require(prm, "type", p + ".type")
        if ptype not in PARAM_TYPES:
            raise ValidationError(p + ".type", "must be 'number' or 'enum'")
        if ptype == "number":
            lo = _bounded_number(prm, "min", p + ".min")
            hi = _bounded_number(prm, "max", p + ".max")
            if lo > hi:
                raise ValidationError(p + ".min", "must not be above max")
        else:
            vals = _require(prm, "values", p + ".values")
            if not isinstance(vals, list) or not vals:
                raise ValidationError(p + ".values", "must be a non-empty list")
            for j, v in enumerate(vals):
                total_chars += _enum_value_chars(v, f"{p}.values[{j}]")
                if total_chars > MAX_TOTAL_VALUE_CHARS:
                    raise too_large

    strat = _require(d, "strategy", "strategy")
    if strat not in STRATEGIES:
        raise ValidationError("strategy", "must be one of: " + ", ".join(STRATEGIES))

    seed = d.get("seed")
    if seed is None:
        seed = DEFAULT_SEED
    elif not _is_int(seed):
        raise ValidationError("seed", "must be an integer")
    out["seed"] = seed
    return out
