"""Butterfly Effect MCP server (stdio). Exposes the deterministic engine as tools.

No network, no file writes, no persistence. stdout is the protocol channel: nothing is printed.
Error text never contains values the user supplied (only field names, fixed messages and
option names, which are labels).
"""
import sys

_SETUP_HINT = (
    "butterfly-effect: the 'mcp' Python package is required (Python 3.10 or newer). "
    "Install it with: python -m pip install mcp"
)

if sys.version_info < (3, 10):
    sys.stderr.write(_SETUP_HINT + chr(10))
    sys.exit(1)

import logging
import warnings
from typing import Any

# The SDK logs the full content of rejected or malformed protocol messages (through the root
# logger and the "mcp" loggers). Figures must never reach a log, so all logging is disabled
# (disabling, not redacting) and warnings are silenced. The one deliberate stderr line is the
# setup hint above, which is written directly and is not a log record.
logging.disable(logging.CRITICAL + 1)
warnings.simplefilter("ignore")

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:
    sys.stderr.write(_SETUP_HINT + chr(10))
    sys.exit(1)

from butterfly_mcp import engine, testmatrix
from butterfly_mcp.schema import ValidationError

mcp = FastMCP("butterfly", log_level="CRITICAL")
for _h in list(logging.getLogger().handlers):  # FastMCP installs a stderr handler; drop it
    logging.getLogger().removeHandler(_h)

ALLOWED_MESSAGES = (
    "simulation time limit exceeded; reduce runs",
    "test matrix time limit exceeded; reduce the parameters or use the random strategy",
)
GENERIC_ERROR = "Unexpected error while processing the request"

SCENARIO_DOC = (
    "scenario is an object with: currency (string); horizon_months (integer 1-600); "
    "income {monthly, variability_pct (optional, percent number 0 to 100)}; savings (number); "
    "fixed_commitments [{name, monthly}] (optional); typical_expenses {monthly} (optional); "
    "options [{name, monthly_cost, upfront, duration_months}] (at least one); "
    "dynamic_events [{name, monthly_probability (a fraction, 0 to 1), amount {low, high} and/or "
    "income_drop_pct (percent number 0 to 100) with duration_months}] (optional); "
    "success_criterion {type: 'never_below', balance (the lowest balance you accept: a timeline succeeds only if the balance never falls below it)}; runs (optional integer, default 10000, "
    "max 100000); seed (optional integer). Option names must be distinct (ignoring case and "
    "surrounding spaces). "
)
STORE_DOC = "Runs locally; the data is not stored or transmitted."


def _expect(value, kind, label, what):
    if kind is str:
        ok = isinstance(value, str)
    else:
        ok = isinstance(value, dict)
    if not ok:
        raise ToolError(f"Invalid input, field '{label}': expected {what}")
    return value


def _call(fn, *args):
    """Run an engine function; turn every failure into a plain tool error. Messages never
    include the received values and no stack trace is returned."""
    try:
        return fn(*args)
    except ValidationError as e:
        raise ToolError(f"Invalid input, field '{e.field}': {e.message}") from None
    except ToolError:
        raise
    except ValueError as e:
        msg = str(e)
        if msg in ALLOWED_MESSAGES:
            raise ToolError(msg) from None
        if msg.startswith("unknown option: "):
            name = msg[len("unknown option: "):]
            if len(name) > 60:
                name = name[:60] + "..."
            raise ToolError("unknown option: " + name) from None
        raise ToolError(GENERIC_ERROR) from None
    except Exception:
        raise ToolError(GENERIC_ERROR) from None


@mcp.tool(description=(
    "Required arguments: scenario and option_name. Simulate ONE option of a decision scenario (seeded, reproducible). " + SCENARIO_DOC +
    "option_name must match the name of one of the options (exact match first, otherwise ignoring "
    "case and surrounding spaces). Returns JSON with the option's "
    "confidence_pct (share of simulated timelines where the criterion holds), end_balance "
    "percentiles, and failure details. " + STORE_DOC))
def run_simulation(scenario: Any = None, option_name: Any = None) -> Any:
    _expect(scenario, dict, "scenario", "an object")
    _expect(option_name, str, "option_name", "a string")
    return _call(engine.run_simulation, scenario, option_name)


@mcp.tool(description=(
    "Required argument: scenario. Simulate EVERY option of a decision scenario and compare them. " + SCENARIO_DOC +
    "Returns JSON with options (per-option results with confidence_pct), recommended, "
    "sensitivity, sensitivity_option, assumptions, seed and method. " + STORE_DOC))
def compare_options(scenario: Any = None) -> Any:
    _expect(scenario, dict, "scenario", "an object")
    return _call(engine.compare_options, scenario)


def _mag(x):
    return f"{x:.0e}".replace("e+", "e")


def matrix_description():
    """Tool description for generate_test_matrix, built from the real limits so it cannot drift."""
    from butterfly_mcp import schema as sc
    from butterfly_mcp import testmatrix as tm

    return (
        "Required argument: test_scenario. Generate deterministic test inputs. "
        "test_scenario is an object with: target (string); "
        "parameters [{name, type: 'number' with min and max, or 'enum' with values}]; "
        "strategy: boundary | equivalence | pairwise | random; seed (optional integer); "
        f"count (optional integer, count 1 to {tm.MAX_RANDOM_COUNT}, default "
        f"{tm.DEFAULT_RANDOM_COUNT}, random strategy only). "
        f"Limits: at most {tm.MAX_PARAMETERS} parameters; parameter type only 'number' or 'enum'; "
        f"names at most {sc.MAX_NAME_LENGTH} characters (target too); "
        f"enum values are scalars (text, number, true/false or null), enum text at most "
        f"{sc.MAX_ENUM_VALUE_LENGTH} characters, at most {tm.MAX_ENUM_VALUES:,} values per enum; "
        f"{sc.MAX_TOTAL_VALUE_CHARS:,} characters in total for names and values; "
        f"number min and max must be finite and at most {_mag(sc.MAX_NUMBER_MAGNITUDE)} in size; "
        "duplicate enum values are removed for the boundary, equivalence and pairwise strategies; "
        "for the random strategy a value listed several times is drawn proportionally more often. "
        "Errors name the offending field (parameters, parameters[i].values, parameters[i].name, "
        "target, count ...); plain limit errors such as too many parameters or values only state the "
        "limit. Pairwise allows at most "
        f"{tm.MAX_PAIRS:,} value pairs across parameters (number parameters count as 3 values) and "
        f"boundary at most {tm.MAX_BOUNDARY_CELLS:,} cases x parameters; the result may hold at most "
        f"{tm.MAX_OUTPUT_CHARS:,} characters of compact JSON (the response as sent is indented and "
        "was measured at about 2 to 3 times that size). Requests over the field limits, the pair "
        "cap and the boundary cap are rejected before any cases are built (field 'parameters' for "
        "the last two, with advice to reduce the parameters or use the random strategy). The "
        "result-size cap is checked while the cases are built (for pairwise this can take up to a "
        "few seconds) and then gives the same advice. "
        f"Generation stops with an error after a {tm.TIME_LIMIT_SECONDS} second time limit, "
        "which bounds that work (it covers generation only). "
        "Returns JSON with strategy, seed, count, cases and notes. " + STORE_DOC
    )


@mcp.tool(description=matrix_description())
def generate_test_matrix(test_scenario: Any = None) -> Any:
    _expect(test_scenario, dict, "test_scenario", "an object")
    return _call(testmatrix.generate_test_matrix, test_scenario)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
