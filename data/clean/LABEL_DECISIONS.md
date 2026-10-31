# Label decisions (debate outcome, 2026-10-31)

Official labels are NEVER changed in the data. Two debaters (keep vs. relabel) converged on:

1. Keep every official label as the training answer: hidden labels come from the same labeller.
2. Labeller rules to document in the report:
   - Topic beats channel: a registration/finance/grades problem stays in that category even when it shows up "in a portal". IT Support = the account/platform/network itself is broken.
   - Low = information requests ("Where/How/copy of/advice").
   - Medium = a concrete malfunction with a workaround.
   - High = a same-day deadline, a safety risk, students stranded, or a DEFINITIVE loss/blocking of enrollment (that last one is beyond the written definition).
   - Ambient fixture (hallway light) = low; equipment in a teaching room = medium (one data point only).
3. Soft targets (argmax preserved, never 50/50) for 3 patterns: hallway light, prerequisite rule, assignment-feedback category. See label_flags.csv.
4. App: a confidence threshold (tuned on CV) + pattern flags send these cases to the human-review queue.
5. Optional: one neutral clarification email to the organizer ("is the low/medium boundary for minor faults and help-requests intentional?"). Do not block on the reply.
6. The URGENT prefix must never change a prediction (robustness test).
