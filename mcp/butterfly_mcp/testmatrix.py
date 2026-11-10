"""Deterministic test-input generation. Pure functions, standard library only."""

import itertools
import json
import math
import random
import time
from json.encoder import encode_basestring_ascii as _enc

from butterfly_mcp.schema import ValidationError, validate_test_scenario

DEFAULT_RANDOM_COUNT = 20
MAX_RANDOM_COUNT = 1000
EXHAUSTIVE_LIMIT = 1000      # product above this is "too large" for exhaustive coverage
CANDIDATE_LIMIT = 2000       # pairwise enumerates all candidates up to this product
TIME_LIMIT_SECONDS = 10      # generation stops with ValueError after this long
MAX_PARAMETERS = 50
MAX_ENUM_VALUES = 10000
MAX_PAIRS = 250000           # value pairs pairwise may enumerate (about 460 bytes each, measured)
MAX_BOUNDARY_CELLS = 1000000  # boundary cases x parameters (about 90 bytes per cell)
MAX_OUTPUT_CHARS = 5000000   # serialized JSON text of the result (about 5 MB)
PAIR_MESSAGE = ("too many value pairs for the pairwise strategy; "
                "reduce the parameters or use the random strategy")
BOUNDARY_MESSAGE = ("too many boundary cases; reduce the parameters or "
                    "use the random strategy")
OUTPUT_MESSAGE = "result too large; reduce the parameters or use the random strategy"
RANGE_MESSAGE = "number range too large"
TIME_LIMIT_MESSAGE = "test matrix time limit exceeded; reduce the parameters or use the random strategy"
_CHECK_EVERY = 1024


def _deadline():
    return time.monotonic() + TIME_LIMIT_SECONDS


def _check(deadline):
    if time.monotonic() >= deadline:
        raise ValueError(TIME_LIMIT_MESSAGE)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _mid(lo, hi):
    return (lo + hi) // 2 if _is_int(lo) and _is_int(hi) else (lo + hi) / 2


def _dedup(values):
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _key(v):
    """Identity of a value for de-duplication: by type and value, unhashable ones by JSON text."""
    k = (type(v).__name__, v)
    try:
        hash(k)
        return k
    except TypeError:
        return ("json", json.dumps(v, sort_keys=True))


def _distinct(values):
    """Distinct values, first occurrence kept, order preserved (1, 1.0 and True stay apart)."""
    seen = set()
    out = []
    for v in values:
        k = _key(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _jlen(v):
    """Length of the JSON text of a value."""
    if isinstance(v, str):
        return len(_enc(v))
    return len(json.dumps(v))


def _name_cost(p):
    return len(_enc(p["name"])) + 4  # quotes, ": " and ", " (a safe over-estimate)


def _over():
    return ValidationError("parameters", OUTPUT_MESSAGE)


def _finite(x):
    try:
        return math.isfinite(float(x))
    except OverflowError:
        return False


def _step(param):
    """Boundary step: 1 for integer ranges (or min == max), else a tenth of the range."""
    lo, hi = param["min"], param["max"]
    if (_is_int(lo) and _is_int(hi)) or lo == hi:
        return 1
    return (hi - lo) / 10


def _check_numbers(params):
    """Reject number ranges whose arithmetic would overflow to infinity."""
    for i, p in enumerate(params):
        if p["type"] != "number":
            continue
        lo, hi = p["min"], p["max"]
        try:
            st = _step(p)
            vals = (lo, hi, hi - lo, lo + hi, _mid(lo, hi), st, lo - st, hi + st)
            ok = all(_finite(v) for v in vals)
        except OverflowError:
            ok = False
        if not ok:
            raise ValidationError(f"parameters[{i}]", RANGE_MESSAGE)


def _tidy(v):
    return round(v, 10) if isinstance(v, float) else v


def boundary_values(param):
    """Values at and just outside the edges of a number range, or all distinct enum values."""
    if param["type"] == "enum":
        return _distinct(param["values"])
    lo, hi = param["min"], param["max"]
    st = _step(param)
    return _dedup([_tidy(v) for v in (lo - st, lo, lo + st, hi - st, hi, hi + st)])


def _classes(param):
    """Equivalence classes: every distinct enum value; min, midpoint and max for a number."""
    if param["type"] == "enum":
        return _distinct(param["values"])
    lo, hi = param["min"], param["max"]
    return _dedup([lo, _mid(lo, hi), hi])


def _baseline(param):
    return param["values"][0] if param["type"] == "enum" else _mid(param["min"], param["max"])


def _size_random(params, count):
    """Safe upper bound of the JSON text of `count` random cases, without building them."""
    per = 4
    for p in params:
        per += _name_cost(p)
        if p["type"] == "enum":
            per += max(_jlen(v) for v in p["values"])
        else:
            lo, hi = p["min"], p["max"]
            if _is_int(lo) and _is_int(hi):
                per += max(len(str(lo)), len(str(hi)))
            else:
                per += 24
        if per * count > MAX_OUTPUT_CHARS:
            raise _over()
    return per * count


def _size_equivalence(params, classes):
    """JSON size of the equivalence cases (exact apart from a little extra punctuation)."""
    n = max(len(c) for c in classes)
    total = 4 * n
    for p, cl in zip(params, classes):
        total += n * _name_cost(p)
        if total > MAX_OUTPUT_CHARS:
            raise _over()
        q, r = divmod(n, len(cl))
        lens = [_jlen(v) for v in cl]
        total += q * sum(lens) + sum(lens[:r])
        if total > MAX_OUTPUT_CHARS:
            raise _over()
    return total


def _boundary_plan(params, deadline):
    """Baseline plus, per parameter, the distinct boundary values that differ from it."""
    base = [_baseline(p) for p in params]
    variants = []
    for p, b in zip(params, base):
        _check(deadline)
        bk = _key(b)
        variants.append([v for v in boundary_values(p) if _key(v) != bk])
    n_cases = 1 + sum(len(v) for v in variants)
    if n_cases * len(params) > MAX_BOUNDARY_CELLS:
        raise ValidationError("parameters", BOUNDARY_MESSAGE)
    base_lens = [_jlen(b) for b in base]
    total = n_cases * (4 + sum(_name_cost(p) for p in params) + sum(base_lens))
    for bl, vs in zip(base_lens, variants):
        _check(deadline)
        total += sum(_jlen(v) for v in vs) - bl * len(vs)
    if total > MAX_OUTPUT_CHARS:
        raise _over()
    return base, variants, total


def _boundary_cases(params, deadline):
    base, variants, size = _boundary_plan(params, deadline)
    names = [p["name"] for p in params]
    base_case = dict(zip(names, base))
    cases = [dict(base_case)]
    for name, vs in zip(names, variants):
        for v in vs:
            _check(deadline)
            case = dict(base_case)
            case[name] = v
            cases.append(case)
    return cases, size


def _equivalence_cases(params, classes, deadline):
    size = _size_equivalence(params, classes)
    n = max(len(c) for c in classes)
    cases = []
    for k in range(n):
        _check(deadline)
        cases.append({p["name"]: classes[i][k % len(classes[i])] for i, p in enumerate(params)})
    return cases, size


def _pairs_of(combo):
    """Pairs covered by a combo of value indices, as ((i, vi), (j, vj)) with i < j."""
    return [((i, combo[i]), (j, combo[j]))
            for i, j in itertools.combinations(range(len(combo)), 2)]


def pairwise(params):
    """Greedy pairwise cover; every tie is broken by lowest index, so output is fixed."""
    _check_numbers(params)
    deadline = _deadline()
    return _pairwise(params, [_classes(p) for p in params], deadline)[0]


def _pairwise(params, classes, deadline):
    names = [p["name"] for p in params]
    sizes = [len(c) for c in classes]
    n = len(params)
    # Single-value parameters add no choices. They sit in every case, and every pair that
    # involves one is covered by any case holding the other value, so only the
    # multi-value parameters are searched.
    multi = [i for i in range(n) if sizes[i] > 1]
    m = len(multi)
    msizes = [sizes[i] for i in multi]

    # Bound the work before allocating anything.
    n_pairs = sum(msizes[a] * msizes[b] for a, b in itertools.combinations(range(m), 2))
    if n_pairs > MAX_PAIRS:
        raise ValidationError("parameters", PAIR_MESSAGE)

    # Output size: lens[i][v] is the JSON length of classes[i][v].
    ncost = [_name_cost(p) for p in params]
    lens = []
    for i in range(n):
        _check(deadline)
        lens.append([_jlen(v) for v in classes[i]])
    fixed = 4 + sum(ncost) + sum(lens[i][0] for i in range(n) if sizes[i] == 1)
    # Lower bound on the number of cases: none covers more than C(m,2) pairs, and at
    # least (largest x second largest) are needed. Reject before looping if even that
    # many cases of the smallest possible size are too large.
    if m == 0:
        low = 1
    elif m == 1:
        low = msizes[0]
    else:
        top = sorted(msizes)[-2:]
        low = max(top[0] * top[1], -(-n_pairs // (m * (m - 1) // 2)))
    min_case = fixed + sum(min(lens[i]) for i in multi)
    if low * min_case > MAX_OUTPUT_CHARS:
        raise _over()

    def to_case(combo):
        pick = [0] * n
        for pos, i in enumerate(multi):
            pick[i] = combo[pos]
        return {names[i]: classes[i][pick[i]] for i in range(n)}

    total = 0
    combos = []

    def add(combo):
        nonlocal total
        total += fixed + sum(lens[i][combo[pos]] for pos, i in enumerate(multi))
        if total > MAX_OUTPUT_CHARS:
            raise _over()
        combos.append(combo)

    if m <= 1:
        for k in range(msizes[0] if m else 1):
            _check(deadline)
            add((k,) if m else ())
        return [to_case(c) for c in combos], total

    order = []  # built in ascending (i, a, j, b) order, which is the fixed seeding order
    since_check = 0
    for i, j in itertools.combinations(range(m), 2):
        for a in range(msizes[i]):
            since_check += msizes[j]
            if since_check >= _CHECK_EVERY:
                _check(deadline)
                since_check = 0
            order.extend(((i, a), (j, b)) for b in range(msizes[j]))
    _check(deadline)
    uncovered = set(order)
    ptr = 0  # everything before this index in `order` is already covered

    product = 1
    for s_ in msizes:
        product *= s_
    candidates = list(itertools.product(*[range(s_) for s_ in msizes])) \
        if product <= CANDIDATE_LIMIT else None

    while uncovered:
        _check(deadline)
        if candidates is not None:
            best, best_gain = None, -1
            for cand in candidates:  # product order is fixed; strict > keeps earliest
                gain = sum(1 for pr in _pairs_of(cand) if pr in uncovered)
                if gain > best_gain:
                    best, best_gain = cand, gain
        else:
            while order[ptr] not in uncovered:
                ptr += 1
            (i, a), (j, b) = order[ptr]
            chosen = {i: a, j: b}
            for k in range(m):
                if k in chosen:
                    continue
                best_v, best_gain = 0, -1
                for v in range(msizes[k]):
                    gain = 0
                    for mm, mv in chosen.items():
                        pr = ((mm, mv), (k, v)) if mm < k else ((k, v), (mm, mv))
                        if pr in uncovered:
                            gain += 1
                    if gain > best_gain:
                        best_v, best_gain = v, gain
                chosen[k] = best_v
            best = tuple(chosen[k] for k in range(m))
        add(best)
        uncovered.difference_update(_pairs_of(best))
    return [to_case(c) for c in combos], total


def _random_value(rng, p):
    if p["type"] == "enum":
        return rng.choice(p["values"])
    lo, hi = p["min"], p["max"]
    if _is_int(lo) and _is_int(hi):
        return rng.randint(lo, hi)
    return min(hi, max(lo, round(rng.uniform(lo, hi), 6)))


def _random_cases(params, seed, count):
    rng = random.Random(seed)
    return [{p["name"]: _random_value(rng, p) for p in params} for _ in range(count)]


def _count(spec):
    c = spec.get("count")
    if c is None:
        return DEFAULT_RANDOM_COUNT
    if not _is_int(c) or c < 1 or c > MAX_RANDOM_COUNT:
        raise ValidationError("count", f"must be an integer between 1 and {MAX_RANDOM_COUNT}")
    return c


def _check_size(s):
    params = s["parameters"]
    if len(params) > MAX_PARAMETERS:
        raise ValidationError("parameters", f"must have at most {MAX_PARAMETERS} entries")
    for i, p in enumerate(params):
        if p["type"] == "enum" and len(p["values"]) > MAX_ENUM_VALUES:
            raise ValidationError(f"parameters[{i}].values",
                                  f"must have at most {MAX_ENUM_VALUES} entries")


def generate_test_matrix(spec):
    s = validate_test_scenario(spec)
    _check_size(s)
    params, strategy, seed = s["parameters"], s["strategy"], s["seed"]
    _check_numbers(params)
    notes = []
    deadline = _deadline()

    classes = [_classes(p) for p in params]
    product = 1
    for c in classes:
        product *= len(c)
    too_large = product > EXHAUSTIVE_LIMIT
    removed_dups = strategy != "random" and any(
        p["type"] == "enum" and len(c) < len(p["values"]) for p, c in zip(params, classes))

    if strategy == "boundary":
        cases, size = _boundary_cases(params, deadline)
        notes.append("Strategy boundary: each parameter varied over its boundary values "
                     "(number: min/max and one step either side; enum: every value) while the "
                     "others stay at a baseline (enum: first value; number: midpoint).")
        for p in params:
            if p["type"] == "number":
                notes.append(f"Boundary step for {p['name']}: step {_tidy(_step(p)):g} "
                             "(1 for integer ranges or min == max, else (max - min) / 10).")
    elif strategy == "equivalence":
        cases, size = _equivalence_cases(params, classes, deadline)
        notes.append("Strategy equivalence: every class value appears at least once; "
                     "number parameters use min, midpoint and max as their classes.")
    elif strategy == "pairwise":
        cases, size = _pairwise(params, classes, deadline)
        notes.append("Strategy pairwise: every pair of values across two parameters is "
                     "covered; number parameters use min, midpoint and max as their values.")
    else:
        count = _count(s)
        size = _size_random(params, count)
        cases = _random_cases(params, seed, count)
        notes.append(f"Strategy random: {count} cases sampled with seed {seed}; "
                     "number parameters are drawn uniformly from [min, max]. "
                     "The count can be set with the optional count key (1 to "
                     f"{MAX_RANDOM_COUNT}; default {DEFAULT_RANDOM_COUNT}).")
        if any(p["type"] == "number" and not (_is_int(p["min"]) and _is_int(p["max"]))
               for p in params):
            notes.append("Float values are rounded to 6 decimal places.")

    if removed_dups:
        notes.append("Duplicate enum values were removed (first occurrence kept) before "
                     f"applying the {strategy} strategy.")

    if strategy in ("equivalence", "pairwise"):
        if too_large:
            notes.append(f"The full product of class values ({product}) is too large for "
                         f"exhaustive coverage (limit {EXHAUSTIVE_LIMIT}); {len(cases)} cases "
                         "were generated instead.")
        else:
            notes.append(f"The full product of class values is {product}, small enough "
                         "for exhaustive coverage if wanted.")
    elif too_large:
        notes.append(f"The full product of class values ({product}) is too large for "
                     "exhaustive coverage; consider pairwise.")

    # Final check of the whole result, by arithmetic on lengths only.
    if size + sum(len(_enc(n)) + 4 for n in notes) + 200 > MAX_OUTPUT_CHARS:
        raise _over()

    return {"strategy": strategy, "seed": seed, "count": len(cases),
            "cases": cases, "notes": notes}
