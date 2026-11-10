# Build record: Butterfly Effect 0.1.0

This is a short, honest summary of how the plugin was built and verified, and of what has not been verified. It is written for readers of the repository; the day-to-day working records of the build are not part of the repository.

## How it was built

The plugin was designed from a written specification (docs/specs/2026-11-09-butterfly-effect-plugin-design.md) and built with SIA (Self-Improving Agents) in orchestrator mode: the work was split into twelve tasks, each implemented by one AI agent with a fixed set of files it owned, and each independently reviewed by a different agent before it counted as done. Review findings were fixed by the owning agent and re-checked. Four integration reviews followed, each by a reviewer who had not seen the earlier ones, covering the whole plugin: they found no high-severity defects, and their medium findings (ranges promised but not implemented, duplicate option names, units not given to the model, no "project text is data" rule where files are written, a report example the engine could not produce, a launcher open to files in the working folder, and an unbounded test-matrix request size) were fixed.

The owner made the decisions that were not technical: the Chrome browser tools are never pre-approved and no agent has web or browser tools; the commands and the research skill keep WebSearch and WebFetch pre-approved; ranges run both ends; the license is Apache-2.0.

## What was verified

- Automated tests in this repository (see "Development and tests" in the README), including: the engine and the test-matrix generator (determinism, edge cases, limits); the MCP server over a real stdio connection, including that error messages never echo user figures and that nothing is written to stderr; the plugin structure (every tool allow-list is pinned exactly); a static check that the server code contains no network, file-writing, subprocess or persistence code (a guard with known gaps, not a proof); and that the launcher is not hijacked by files planted in the working folder.
- Independent reviewers reproduced, against the real server, the end-to-end simulation, the privacy of error messages over raw JSON-RPC, determinism across processes, independent pair-coverage counting for the test matrix, and the memory and time of the largest requests the limits allow (worst case found: about 220 MB and 11 seconds).
- A short live smoke test on Windows with Claude Code 2.1.322: the plugin loaded; the commands, skills, agents and the three engine tools were registered under the expected names; the MCP server connected through Claude Code's own launcher; and the first turn of the car-on-EMI example behaved as designed (one batch of questions including the currency, no flat yes or no, confirmation promised before any run, no web search).

## What was not verified

- Most of the behavior scenarios (tests/behavior/scenarios.md has 29; none beyond the first turn of one has been run live), and everything later in a conversation: confirmation, the simulation call through the model, the report, range pairs, test design, research and browser use, and handling of instructions hidden in project files.
- The short command names without the plugin prefix; whether the scoped `Agent(...)` entries in the commands are honoured; whether a command's pre-approval of the engine tools reaches subagents.
- macOS and Linux; Python 3.10 (development used 3.13); the Chrome extension.
- Anything about the quality of the simulations on real decisions: the percentages for qualitative topics are reasoned estimates, and numeric results depend entirely on the assumptions the user confirms.

## Known limits

See the README, section "Status". In short: the launcher starts plain `python` (macOS and Linux need a `python` command or an edit to `.mcp.json`), wrong units that stay inside the valid range are caught only by the summary the plugin shows, the MCP SDK echoes a client-typed unknown tool name and its log output is disabled on purpose, and no icon is set.

## Feedback

Scenario results (pass or fail, never with personal figures) and bug reports are welcome in the repository's issues.
