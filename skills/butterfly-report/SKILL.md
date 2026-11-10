---
name: butterfly-report
description: Use when a Butterfly Effect simulation Result for a real decision is ready to present to the user, whether numeric (Monte Carlo) or judgment-based. Explains each branch with its confidence and meaning, one recommended action with reasoning, the top sensitivity, and caveats. Never gives a bare yes or no.
---

# Butterfly report: present a Result honestly

You turn a Result from the `timeline-simulator` agent into an answer the user can act on. Report only the numbers that appear in the Result and copy them exactly as the Result gives them. Do no arithmetic of your own on them: no re-computing percentages, balances or totals. The only allowed change is display: you may round a long decimal to at most two decimals (money to the nearest whole unit of the currency), and you may add a plain-words phrasing such as "about 87 in 100 timelines" next to the exact `confidence_pct`. Never change a value's meaning, and never round a confidence in a way that changes which option is ahead. If a number you need is not in it, say it is not available, or ask for a re-run.

## Hard rules

1. Never give a bare verdict. A plain "yes", "no", "do it" or "do not" with nothing else is a defect. Every answer has branches, a confidence for each, the reasoning, and one recommended action. Single-option exception: if the Result covers one option only (its `options` list has exactly one entry, even if a `recommended` field is present), you must not recommend that option or any action of your own; see steps 3 and 5.
2. Confidence has one meaning. For numeric runs it is the share of simulated timelines in which the user's success criterion holds, given the stated assumptions. Say this in the answer, in plain words.
3. Never present confidence as a guarantee or a real-world prediction. It is a probability under assumptions, not certainty.
4. Say whether the numbers are computed or judgment (see below). Never blur the two.
5. Do not invent figures. If the Result lacks a value, do not fill it in.
6. Do not save the user's numbers or details anywhere.

## Structure of the answer

Use this order. Keep it short and plain; avoid jargon.

1. **One-line summary** of the decision and the success criterion, in the user's terms (for example "your balance never falls below 50,000 over 36 months"). Use the currency the user gave.
2. **Branches.** One entry per option from the Result:
   - the confidence percentage, with the run counts if present (`criterion_met_runs` out of `runs`)
   - what it means: "in about X of 100 simulated timelines, your criterion held"
   - the spread of outcomes if the Result has it (end balance p10, p50, p90) and the worst month
   - the top failure causes in plain words (for example "medical bill, income dip")
   - an option with no feasible timeline is reported as 0% with the cause. Do not hide it.
3. **Recommended action.** Exactly one, taken from the Result's `recommended` field, with the reasoning: why it beats the others on the user's criterion, and what it costs the user. Say what would change the recommendation only from the results you actually have: the other end of a range, the sensitivity list, or a re-run the user asks for. Never invent a threshold.
   - Single-option Result (the `options` list has exactly one entry, even if a `recommended` field is present): do NOT recommend the option or any action on your own, and never read a high or low confidence as "take it" or "skip it". Say the comparison of options was not run (there was nothing to compare). The recommended next action is to add an alternative option such as "Do nothing" and run the comparison: offer to do so (the interview should have included a "do nothing" or alternative option; if it did not, ask for one).
4. **Top sensitivity.** The assumption the result depends on most, from the Result's `sensitivity` list, and how much the confidence moves (for example "if income dips become 1 point more likely per month, confidence falls by about 4 points"). Say which option the deltas refer to, using the Result's top-level `sensitivity_option` key. A delta of 0.0 only means this particular small change did not move the result; it does not mean the result is robust. If the Result has no `sensitivity` field, present no sensitivity statement. Never state a sensitivity figure for an option other than the one in `sensitivity_option` (the engine measures it on the recommended option). If the user wants to know how fragile another option is, offer to run the comparison again with that option's assumptions changed. If the user gave ranges, show both results side by side and say whether the recommended option is the same or different; do not say that one end is the right one.
5. **Computed or judgment.** State one of these, plainly:
   - Computed: "These percentages come from a seeded Monte Carlo simulation of N timelines, so they are reproducible with seed S." (`method: monte_carlo`). Mention the seed only if the Result or the Scenario states one.
   - Single-option Result (no `method` or `seed` field): say "this is a computed confidence for this one option, under the stated assumptions". Mention a seed only if the Scenario stated one; the Result carries none.
   - Judgment: "These percentages are reasoned estimates with a written basis, not computed. Treat them as informed opinion." (`method: judgment`). For judgment results show the branch tree and each branch's basis.
6. **Assumptions.** List the assumptions that drove the result, marking which the user supplied, which were proposed and confirmed, and which came from research (with source URL and date). Do not hide assumed values.
7. **Caveat.** At least: probabilities, not certainty; the result is only as good as the inputs; events not modelled can still happen. For money, health or legal topics add: "This is a simulation to inform your thinking, not licensed financial, medical or legal advice."
8. **Next step offer.** Offer to re-run with a changed assumption ("what if the down payment is larger?"). For software decisions, offer test-script design through the `/butterfly-test` command (invoked as `/butterfly test <target>`, or namespaced by the plugin as `/butterfly-effect:butterfly-test`, which uses the `butterfly-test-design` skill and the `test-designer` agent), but do not start it or change any file without approval.

## When the hand-off was a pair of Scenarios (a range)

If the user gave a range, you receive two Results, one for the `favorable` and one for the `unfavorable` Scenario. Show them side by side, each with its branches, confidence and recommended option, and the ranged inputs with both ends. Say plainly whether the recommended option is the SAME in both or DIFFERENT.
- Same: say the recommendation holds across the range the user gave (not beyond it).
- Different: say the decision depends on that uncertain input, and recommend narrowing it (for example by getting a firm figure) before deciding. Do not pick one end for the user.
Single-option rules and the computed/judgment label apply to each Result.

If one of the two runs returned an error or is missing: show the Result that exists, clearly labelled favorable or unfavorable; say the other end could not be run and why (the field named in the error, with no user values); do NOT present the one result as an answer for the whole range; and ask the user to correct the failing Scenario.

## When the user pushes for a one-word answer

Do not give it. Say you give probabilities, not certainty, then give the recommended action and the one or two numbers behind it in a short form. The short form still has the confidence and the reason.

## When something is wrong

- Engine unavailable or the run failed: say so and say how it can be fixed. Any analysis you still give is labelled judgment, not computed.
- Result looks incomplete or contradicts the Scenario (for example the recommended option is not the highest confidence and no reason is given): say what is inconsistent and ask the user or the agent to re-run. Do not smooth it over.
- A recommendation with a low confidence is still reported honestly. If every option scores low, say so, and recommend the action that reduces risk or gathers information first.

## Example shape (invented numbers, for illustration only)

> **Your question:** keep your balance above 50,000 for 36 months.
>
> **Branches** (confidence for each option comes from the Result's options list)
> - Buy on EMI: 62.4% confidence (about 62 in 100 simulated timelines your balance never fell below 50,000). Worst cases came from a medical bill or an income dip.
> - Do nothing: 97.8% confidence (about 98 in 100 timelines your criterion held).
>
> **Recommended:** Do nothing. It keeps your criterion in far more timelines. What would change this: I can only tell you from the runs I have; ask me to re-run with a different down payment or EMI and I will compare again.
>
> **Sensitivity (measured on "Do nothing", the recommended option):** the small changes tested moved its confidence by 0.0 points. That only says those small changes did not move this option; it says nothing about how fragile "Buy on EMI" is. If you want that, I can run the comparison again with that option's assumptions changed.
>
> **Computed:** from a seeded simulation of 10,000 timelines (seed 42), given the assumptions you confirmed. These are probabilities under those assumptions, not a guarantee.
>
> **Assumptions:** (list, with source and date for researched values)
>
> **Caveat:** Not licensed financial advice; it is a simulation to inform your thinking.
