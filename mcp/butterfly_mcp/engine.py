"""Seeded Monte Carlo simulation and option comparison.

Pure computation, standard library only: no I/O of any kind.
"""

import copy
import random
import time

from butterfly_mcp.schema import validate_scenario

TIME_LIMIT_SECONDS = 20
_CHECK_EVERY = 64
BASELINE_CAUSE = "baseline cash flow"
TOP_CAUSES = 3


def _percentile(sorted_vals, p):
    """Nearest-rank percentile of an ascending list; p in (0, 100]."""
    n = len(sorted_vals)
    rank = max(1, -(-p * n // 100))  # ceil(p*n/100)
    return sorted_vals[min(n, int(rank)) - 1]


def _simulate(sc, option, deadline):
    """Run sc['runs'] timelines for one option dict. Returns raw aggregates."""
    rng = random.Random(sc["seed"])
    horizon = sc["horizon_months"]
    income = sc["income"]["monthly"]
    var = (sc["income"].get("variability_pct") or 0) / 100.0
    fixed = sum(c["monthly"] for c in sc.get("fixed_commitments") or [])
    fixed += (sc.get("typical_expenses") or {}).get("monthly", 0)
    events = sc.get("dynamic_events") or []
    floor = sc["success_criterion"]["balance"]
    opt_cost, opt_dur = option["monthly_cost"], option["duration_months"]
    start = sc["savings"] - option["upfront"]
    runs = sc["runs"]

    ev = [(e["name"], e["monthly_probability"],
           (e["amount"]["low"], e["amount"]["high"]) if e.get("amount") else None,
           e.get("income_drop_pct"), e.get("duration_months", 0)) for e in events]

    met = 0
    ends = []
    worst = None
    causes = {}
    uniform = rng.uniform
    rand = rng.random

    for r in range(runs):
        if r % _CHECK_EVERY == 0 and time.perf_counter() >= deadline:
            raise ValueError("simulation time limit exceeded; reduce runs")
        bal = start
        run_worst = bal
        failed_cause = None
        failed = bal < floor
        if failed:
            failed_cause = BASELINE_CAUSE
        drops = []  # active income drops as [pct, months_remaining]
        last_event = None
        for m in range(1, horizon + 1):
            # Always draw the same number of random values per month so that
            # runs of different options and sensitivity variants stay aligned.
            fired_amount = 0.0
            fired_name = None
            for name, prob, amt, dpct, dur in ev:
                hit = rand() < prob
                u = uniform(0.0, 1.0)
                if not hit:
                    continue
                fired_name = name
                if amt is not None:
                    fired_amount += amt[0] + (amt[1] - amt[0]) * u
                if dpct is not None:
                    drops.append([dpct, dur])
            noise = uniform(-var, var) if var else 0.0
            inc = max(0.0, income * (1.0 + noise))
            if drops:
                inc = max(0.0, inc * (1.0 - max(d[0] for d in drops) / 100.0))
                for d in drops:
                    d[1] -= 1
                drops = [d for d in drops if d[1] > 0]
            bal += inc - fixed - fired_amount - (opt_cost if m <= opt_dur else 0)
            if fired_name is not None:
                last_event = fired_name
            if bal < run_worst:
                run_worst = bal
            if not failed and bal < floor:
                failed = True
                failed_cause = fired_name or last_event or BASELINE_CAUSE
        ends.append(bal)
        if worst is None or run_worst < worst:
            worst = run_worst
        if failed:
            causes[failed_cause] = causes.get(failed_cause, 0) + 1
        else:
            met += 1
    ends.sort()
    return met, ends, worst, causes


def _result(name, sc, option, deadline):
    met, ends, worst, causes = _simulate(sc, option, deadline)
    runs = sc["runs"]
    ranked = sorted(causes.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "name": name,
        "confidence_pct": round(100.0 * met / runs, 2),
        "criterion_met_runs": met,
        "runs": runs,
        "end_balance": {"p10": _percentile(ends, 10), "p50": _percentile(ends, 50),
                        "p90": _percentile(ends, 90)},
        "worst_month_balance": worst,
        "top_failure_causes": [k for k, _ in ranked[:TOP_CAUSES]],
    }


def _find(sc, option_name):
    for o in sc["options"]:
        if o["name"] == option_name:
            return o
    key = str(option_name).strip().casefold()
    for o in sc["options"]:  # names are unique after strip + casefold (schema)
        if o["name"].strip().casefold() == key:
            return o
    raise ValueError(f"unknown option: {option_name}")


def run_simulation(scenario, option_name):
    sc = validate_scenario(scenario)
    option = _find(sc, option_name)
    deadline = time.perf_counter() + TIME_LIMIT_SECONDS
    return _result(option["name"], sc, option, deadline)


def compare_options(scenario):
    sc = validate_scenario(scenario)
    deadline = time.perf_counter() + TIME_LIMIT_SECONDS
    results = [_result(o["name"], sc, o, deadline) for o in sc["options"]]
    best = max(results, key=lambda r: (r["confidence_pct"], r["end_balance"]["p50"]))
    rec_option = _find(sc, best["name"])

    sensitivity = []
    for i, e in enumerate(sc.get("dynamic_events") or []):
        if e["monthly_probability"] >= 1.0:
            continue  # +1pp cannot change a probability that is already 1
        alt = copy.deepcopy(sc)
        p = alt["dynamic_events"][i]
        p["monthly_probability"] = min(1.0, p["monthly_probability"] + 0.01)
        c = _result(best["name"], alt, rec_option, deadline)["confidence_pct"]
        sensitivity.append({"assumption": f"{e['name']} probability", "change": "+1pp",
                            "confidence_delta_pct": round(c - best["confidence_pct"], 2)})
    alt = copy.deepcopy(sc)
    alt["income"]["monthly"] = sc["income"]["monthly"] * 0.95
    c = _result(best["name"], alt, rec_option, deadline)["confidence_pct"]
    sensitivity.append({"assumption": "monthly income", "change": "-5%",
                        "confidence_delta_pct": round(c - best["confidence_pct"], 2)})

    assumptions = [
        "Confidence is the share of simulated timelines in which the balance never "
        f"falls below {sc['success_criterion']['balance']} {sc['currency']}, given these inputs; it is not a guarantee.",
        f"{sc['runs']} timelines over {sc['horizon_months']} months, seeded with {sc['seed']}; "
        "the same input and seed give identical output.",
        "Each option is simulated with the same random draws.",
        "Upfront cost is paid at month 0; monthly cost is paid in months 1 to duration_months.",
        "Event amounts are uniform between low and high. Each income drop keeps its own "
        "percentage and remaining duration; in any month the largest active drop applies. "
        "Income never goes below 0.",
        "worst_month_balance is the lowest balance seen in any single run in any month "
        "(an extreme-case figure, not an average).",
        "A failed timeline is blamed on the event that fired in the breach month, else the "
        "most recent event that fired earlier in that run (possibly many months before), "
        "else baseline cash flow.",
        "A sensitivity delta of 0.0 only means this particular small change did not move the "
        "result; it is not proof of robustness.",
        "Recommended is the option with the highest confidence; tie rule: ties are broken "
        "by the higher median (p50) end balance, then by listed order.",
        f"Sensitivity is measured on the recommended option ({best['name']}).",
        "This is a simulation to inform thinking, not professional advice.",
    ]
    return {"options": results, "recommended": best["name"], "sensitivity": sensitivity,
            "assumptions": assumptions, "sensitivity_option": best["name"], "seed": sc["seed"], "method": "monte_carlo"}
