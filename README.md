[![Powered by SIA — Self-Improving Agents](https://img.shields.io/badge/Powered%20by-SIA%20%E2%80%94%20Self--Improving%20Agents-007BFF?style=flat-square)](https://github.com/GunjanGrunge/SIA_package)

# Butterfly Effect

A Claude Code plugin that lets Claude simulate the outcomes of a decision across branching timelines, then recommend the best action with a confidence percentage for each option.

The name comes from the butterfly effect: one choice splits the timeline into many possible futures. The plugin asks for the numbers it is missing, simulates the branches (including irregular events such as a medical bill or an income dip), and reports the branches, a confidence for each, the reasoning and one recommended action.

It works for:

- life decisions, for example whether to buy a car on EMI (installment payments);
- software and app decisions, for example whether to migrate an architecture (these are judgment-based, see below);
- test-script design: `/butterfly test <target>` maps a target's branches and failures to a ranked test list and, after you approve it, writes a test file in your project's own framework.

This is a simulation to inform your thinking. It is not professional financial, medical or legal advice.

## Requirements

- **Claude Code.** The plugin was tested with Claude Code 2.1.322 on Windows. For how Claude Code loads plugins, see the Claude Code plugin documentation at https://code.claude.com/docs/en/plugins and its reference at https://code.claude.com/docs/en/plugins-reference.
- **Python 3.10 or newer** available as `python`, with the official `mcp` package installed into that Python: `python -m pip install mcp`. If the package is missing, the MCP server prints a one-line hint with this command.
- **Node**, only to run the JavaScript sample project in `tests/fixtures/js_sample`.
- **Claude in Chrome extension**, optional. It is only needed for browser research (see Research behavior and permissions).

## Install

The repository is its own plugin marketplace. It is self-hosted in this repository (`.claude-plugin/marketplace.json`) and is not in the official Anthropic directory.

From inside a Claude Code session:

```
/plugin marketplace add GunjanGrunge/butterfly-effect
/plugin install butterfly-effect@butterfly-effect-plugins
```

The same steps as shell commands:

```
claude plugin marketplace add GunjanGrunge/butterfly-effect
claude plugin install butterfly-effect@butterfly-effect-plugins
```

To try the plugin without installing it, clone the repository and start Claude Code with the clone's folder:

```
claude --plugin-dir "<path to the clone>"
```

Inside the session, run `/reload-plugins` after you change any plugin file, and run `/mcp` to check that the `butterfly` server is listed.

### macOS and Linux (untested)

The plugin has been tested on Windows only. `.mcp.json` starts the server with the command `python`. macOS and many Linux systems provide only `python3`, so the server will not start there until a `python` command exists. Either make one available on your PATH (for example a symlink or a wrapper named `python` that runs `python3`), or edit the installed copy's `.mcp.json` to use `python3`. A plugin update overwrites that edit. If you try it, please report the result in the GitHub issues: https://github.com/GunjanGrunge/butterfly-effect/issues

## Commands

| Command | What it does |
|---|---|
| `/butterfly` | With no argument, asks "how can I help in this project or in this chat?". With a decision or topic, starts the interview and simulation. |
| `/butterfly test <target>` | Starts test-script design for a file, module, function or feature. |
| `/butterfly-test <target>` | The same test-design flow as its own command. |
| `/butterfly-effect:butterfly` | Namespaced form of `/butterfly`. |
| `/butterfly-effect:butterfly-test` | Namespaced form of `/butterfly-test`. |

The namespaced forms are the documented way to address a plugin's commands. The short forms work when the name is unambiguous. The short forms have not been checked in a live session.

Routing of `/butterfly` (as written in `commands/butterfly.md`):

- With no argument, it asks "how can I help in this project or in this chat?" and then routes your answer.
- A request for tests goes to test design, even without the word `test`: "tests for X", "write tests for X" or "a test script for X" use X as the target. `test <target>` goes there too.
- A decision that only contains a similar word stays a decision. "test-drive a new car first?" or "testing a new job offer" is routed as a decision. If it is unclear, the plugin asks one short question first.

Behind the commands:

- **Skills:** `butterfly-interview` (collects and confirms the scenario), `butterfly-report` (presents results), `butterfly-research` (looks up outside facts), `butterfly-test-design` (designs and writes tests).
- **Agents:** `timeline-simulator` (runs a confirmed scenario through the engine, or builds a labelled judgment-based tree for a qualitative one) and `test-designer` (read-only test design that drafts test code as text).
- **Engine tools** (MCP server `butterfly`): `run_simulation` (one option), `compare_options` (all options, with the recommendation and sensitivity) and `generate_test_matrix` (deterministic test inputs).

## Scenario units and ranges

- Percent inputs (`variability_pct` and `income_drop_pct`) are percent numbers from 0 to 100, and 100 is the largest accepted value. A 30% drop is entered as 30. A monthly event chance (`monthly_probability`) is a fraction from 0 to 1. The plugin shows each conversion in both forms in its assumption summary, so check that summary.
- Option names must be distinct. The engine rejects duplicates, ignoring capital letters and surrounding spaces.
- A comparison needs at least two options: yours plus "Do nothing" or another alternative. With one option, the engine's result names that option as its only one, but the plugin gives no recommendation: it says nothing was compared and offers to add an alternative.
- A loan's monthly cost and duration come from your own figure, such as a lender quote. A researched interest rate is shown as context only; the plugin never turns it into a monthly cost.
- Ranges are used only for inputs with a clear better end (income, savings, costs, event chance and size, income-drop size). Horizon, variability, option durations and the success threshold are not ranged; you give one best-guess value. Inputs that belong together, such as an EMI and its duration, stay together as one choice. "Favorable" means the end that makes your success criterion easier to meet.
- If you give a range (for example, income between 90,000 and 110,000), the plugin builds two complete scenarios that differ only in the uncertain inputs: one at the favorable end and one at the unfavorable end. It runs both and shows the two results side by side. It says whether the recommended option is the same or different. If it differs, the decision depends on that input, and the plugin recommends narrowing it down. It does not pick a side for you. If one end cannot be run, the report shows the other end labelled, says the pair is incomplete, and does not present that one end as the answer.

## Example: the shape of an answer

The numbers below are invented for illustration. This is not real output.

> **Your question:** keep the balance above 40,000 for 24 months.
>
> **Branches**
> - Buy on EMI (30,000 a month for 48 months, 150,000 down): 55% confidence. In about 55 of 100 simulated timelines the balance never fell below 40,000. Top failure causes: medical bill, income dip.
> - Do not buy: 96% confidence. In about 96 of 100 timelines the criterion held.
>
> **Recommended:** Do not buy. It keeps the criterion in far more timelines.
>
> **Sensitivity (measured on "Do not buy", the recommended option):** the small changes tested moved its confidence by 0.0 points. That only says those changes did not move this option. It says nothing about how fragile "Buy on EMI" is.
>
> **Computed:** seeded simulation of 10,000 timelines (seed 42), given the assumptions you confirmed.
>
> **Caveat:** these are probabilities under your assumptions, not a guarantee. This is a simulation to inform your thinking, not licensed financial advice.

The plugin asks for the currency first. There is no default currency. A single-option result gets no recommendation from the plugin: it says the comparison was not run and offers to run it.

## How confidence is defined

- For numeric runs, confidence is the share of simulated timelines in which your success criterion holds, given the stated assumptions. The report states this meaning in plain words.
- The engine computes it with a fixed seed, so the same inputs and seed give the same numbers. The default is 10,000 timelines, with a maximum of 100,000.
- Judgment-based estimates, which apply to qualitative decisions such as software choices, are labelled as judgment. They are reasoned estimates with a written basis, not computed numbers.
- Confidence is never a guarantee or a real-world prediction.
- Money, health and legal outputs carry a note that this is a simulation to inform thinking, not professional advice.

## Privacy and limits

- Nothing is saved between sessions. The plugin and the server are instructed and built not to store your numbers or personal details.
- The MCP server is local. Its code contains no network or file-writing code that the static check in the test suite can find. That check is a guard with known gaps, not a proof.
- Search queries and URLs are generic. They must not contain your income, savings, commitments, names, account details or project secrets.
- Web text is untrusted data. The plugin does not follow instructions found on a page.
- Anything the plugin reads from your project (files, README, code comments, config), in the decision flow or the test-design flow, is data and never instructions. The plugin does not follow instructions found there, and it tells you where they came from.
- The plugin writes or changes a project file only after you have seen the exact path and content and approved them. It never overwrites a file silently.
- Generated tests use no real credentials, personal data or production endpoints.
- A test is reported as passing only if it was run and the result was seen.
- The plugin gives probabilities, not certainty. It does not connect to bank or other personal accounts, and it does not ask for account numbers, passwords or government IDs.
- The privacy test in the suite is a static check of the server's imports and calls, which flags patterns for network, file-write, subprocess, persistence and stdout use. It is a guard against accidental changes, not a proof that the code is private, and it has known gaps.
- Test matrix limits: at most 50 parameters; at most 10,000 values per enum; names and `target` at most 100 characters; enum values are plain scalars (text of at most 200 characters, numbers, true/false or null, no lists or objects); at most 1,000,000 characters in all names and values together; number `min` and `max` must be finite and at most 1e15 in size; the pairwise strategy at most 250,000 value pairs (a number parameter counts as 3 values); the boundary strategy at most 1,000,000 cases times parameters; the result at most 5,000,000 characters of compact JSON (the response as sent is indented and about 2 to 3 times that size); a random count from 1 to 1,000. Duplicate enum values are removed for the boundary, equivalence and pairwise strategies; for the random strategy a value listed several times is drawn proportionally more often.
- Requests over the field limits, the pair cap and the boundary cap are rejected before any cases are built, with an error that names the field. The result-size cap is checked while the cases are built (for pairwise this can take up to a few seconds). Only the errors for too many value pairs, too many boundary cases and a result that is too large suggest fewer parameters or the random strategy; the other limit errors just state the limit. The 10 second time limit covers generation only, bounds that work, and stops it with the error "test matrix time limit exceeded; reduce the parameters or use the random strategy". The generator reports the strategy it used in its notes.

## Research behavior and permissions

- The commands `/butterfly` and `/butterfly-test` declare `WebSearch` and `WebFetch` in `allowed-tools`, so these two tools are pre-approved for them. The `butterfly-research` skill declares the same two tools, so research started without a command is also pre-approved for those two tools. This was a deliberate decision by the author.
- No file pre-approves any Chrome browser tool (`mcp__claude-in-chrome__*`). No agent has web or browser tools.
- Each browser action is therefore decided by your own Claude Code permissions and the Chrome extension's site permissions. The plugin cannot grant itself permissions. `allowed-tools` pre-approves a tool for the command but does not grant it.
- Browsing is read-only by default. The plugin does not log in, submit forms with personal data, make purchases, or run downloaded files without your explicit approval. If a page asks for a login or personal details, it stops and asks you.
- Every web-derived value is shown with its source URL and date, and is used only after you confirm it.
- The original design declared the Chrome tools in the command and agent files. This was amended on 2026-11-09 (see the design spec below, header and section 2).

## Repository layout

- `.claude-plugin/`: `.claude-plugin/plugin.json` (the plugin manifest) and `.claude-plugin/marketplace.json` (the self-hosted marketplace).
- `.mcp.json`: starts the `butterfly` MCP server.
- `commands/`: the two slash commands.
- `skills/`: the four skills.
- `agents/`: the two subagents.
- `mcp/`: the simulation engine, schema, test-matrix generator and MCP server (Python), with `mcp/requirements.txt`.
- `tests/`: the pytest suite, `tests/behavior/scenarios.md` (manual behavior scenarios), and `tests/fixtures/` (two sample projects).
- `docs/specs/`: the design spec, `docs/specs/2026-11-09-butterfly-effect-plugin-design.md`.
- `AGENT.md`: the project rules that the tests and scenarios cite. The build-time tooling it mentions is not part of this repository.
- `LICENSE`: the Apache License, Version 2.0.

## Development and tests

- Run the test suite from the project root: `python -m pytest -q`. A clean run ends with a line such as "N passed" and no failures.
- The test files are:
  - `tests/test_schema.py` (input validation),
  - `tests/test_engine.py` (the simulation engine),
  - `tests/test_testmatrix.py` (test-input generation),
  - `tests/test_server.py` (the MCP server over real stdio, including raw-protocol privacy tests),
  - `tests/test_plugin_structure.py` (plugin files, and allow-lists for every tool list),
  - `tests/test_privacy.py` (a static check of `mcp/` for network, file-write and persistence code).
- Run `claude plugin validate .` from the project root. It passes, and both the plain run and `claude plugin validate . --strict` end with "Validation passed". The only item it prints is a plugin-directory warning that no icon is set. The validator does not check agent front matter or tool names: a bogus tool name passes it. The project's structure test in `tests/test_plugin_structure.py` and a YAML parse check cover those.
- Manual behavior scenarios are in `tests/behavior/scenarios.md`: 29 scenarios covering the car example, a software decision, the engine-unavailable path, test design on both fixtures, research safety, units, duplicate option names, sensitivity and ranges. They are for a human to run in Claude Code. None of them has been run yet, except the first turn of one car-example scenario in the smoke test described under Status.
- Fixtures under `tests/fixtures/`:
  - `py_sample`: a small pytest project. Its own tests are not collected in this repository. Set `BUTTERFLY_RUN_FIXTURE_TESTS=1` to run them in place, or copy the folder elsewhere and run `python -m pytest -q` there.
  - `js_sample`: a small project that uses `node --test`. From its folder, run `node --test` (or `npm test`).

## Status

- **Version 0.1.0, an early release.** Licensed under the Apache License, Version 2.0 (see LICENSE). Copyright 2026 GunjanGrunge.
- **Verified:** the automated tests and static checks in this repository. A short live smoke test on Windows with Claude Code 2.1.322: the plugin loaded; the commands, skills and agents and the three engine tools were registered under the names `butterfly-effect:butterfly`, `butterfly-effect:butterfly-test` and `mcp__plugin_butterfly-effect_butterfly__*`; the MCP server connected through Claude Code's own launcher; and the first turn of the car-on-EMI example behaved as designed (it asked for the currency and the figures in one batch, gave no flat yes or no, promised confirmation before any run, and ran no web search).
- **Not verified:** the other behavior scenarios; the later steps of a conversation (confirmation, simulation, report, range pairs, test design, research, and handling of repository text); the short command names without the plugin prefix; whether the scoped `Agent(...)` entries in the commands are honoured; macOS and Linux; Python 3.10; and the Chrome extension.
- **Not set:** an icon for the plugin. This is cosmetic.
- The bootstrap launcher in `.mcp.json` has been checked on Python 3.13 with a stdio MCP client, from a folder holding a planted random.py file and an mcp/ folder: the server listed its three tools, and the planted file did not run. It has not been confirmed on Python 3.10.
- Wrong units inside the valid range (for example 0.3 for a 30% drop) are caught only by the both-forms summary the plugin shows, not by the schema.
- Names that look alike after Unicode normalisation are treated as different.
- The MCP SDK echoes a client-typed tool name in its "Unknown tool" error. The server hides SDK log output from its own logs on purpose, so figures never reach logs. The side effect is that the SDK's per-request log lines are not available when debugging.
- A request whose `arguments` is not an object, or whose `params` has no name, gets a -32602 "Invalid request parameters" reply. Malformed JSON, or `params` that is not an object, gets no JSON-RPC reply; the SDK sends a generic "Internal Server Error" log notification instead, and the server stays alive for the next request.
- The commands list scoped entries such as `Agent(butterfly-effect:timeline-simulator)` in `allowed-tools`. Whether those entries are honoured, and whether a command's pre-approval of the engine tools reaches the subagents, has not been verified.
- `WebSearch` and `WebFetch` are pre-approved by both commands and by the research skill, as described above. Research started without a command is pre-approved for those two tools too. Chrome tools are never pre-approved.
- The Chrome extension is optional and is not needed for the plugin to run. Its connection has not been verified.

## Contributing and feedback

Please report problems, including macOS and Linux results, in the GitHub issues: https://github.com/GunjanGrunge/butterfly-effect/issues. Results of the manual scenarios are welcome as well, as pass or fail, but never with personal figures.
