# AI Quest 2026 — Student Challenge Guide (official, copied from the student pack)

## Scenario and task
Create a smart triage tool for **fictional student helpdesk requests**. Given a request, predict one of six categories: Registration; IT Support; Finance; Transportation; Facilities; Academic Support. Track B/C also predict priority: low, medium, high. Priority labels are based on the example's stated urgency/impact, not official university policy. The tool must never claim to contact a real department.

## Tracks
**A — Starter:** Category classification + notebook + simple demonstration. Use a transparent baseline such as TF-IDF and Logistic Regression or Naive Bayes.
**B — Builder:** Category + priority classification; show a confusion matrix and compare at least two methods.
**C — Innovator:** All B requirements + runnable interactive app, support for Arabic/English inputs where feasible, error analysis and explainability; optional pretrained models allowed with disclosure.

Teams select one track during registration, and cannot change after 3 November without organizer approval. Teams comprise 2–3 currently enrolled students. Students must disclose external services and pretrained models; copied code without attribution is prohibited. No real students' personal data may be uploaded.

## Data
train.csv and validation.csv include request_id, text, category, priority. Fictional templated examples are **synthetic demonstration data**, NOT a verified real university dataset. Templates can make evaluation artificially easy. Scenario families are held apart across splits to reduce near-duplicate leakage. The organizers hold hidden_test.csv and its labels. The hidden set evaluates generalization to held-out scenarios, but cannot support claims of real-world deployment readiness.

## Required submission by Tuesday 10 November, 23:59 Asia/Amman
1. Source code or notebooks; dependencies and README with clean run instructions.
2. predictions.csv with columns request_id, category, priority for the organizer-released blind test; Starter may put 'not_applicable' for priority. Organizers will provide hidden test input securely during judging, or run the team's inference script.
3. Maximum 2-page PDF report: data approach, chosen model, validation results, limitations and source attribution.
4. Demo video no longer than 3 minutes.
5. Track C: link or package of runnable local/hosted application.

## Baseline and fairness
No external private data; public pretrained models allowed with attribution; no requirement for paid compute or APIs; a standard laptop CPU baseline is accepted. Judges may run the submissions on a common computer and request a short clarification.

## Common category definitions
- Registration: course enrollment, prerequisite or add/drop problems
- IT Support: account, network or learning platform problems
- Finance: fees, invoices, scholarships, receipts
- Transportation: shuttles, buses, routes, passes
- Facilities: rooms, power, leaks, equipment, physical infrastructure
- Academic Support: advising, grades, schedules, academic assistance

## Priority definitions (synthetic labels)
High = immediate deadline, safety risk or major interruption; Medium = concrete service issue without immediate severe impact; Low = general question or routine information request. Human review should override uncertain predictions.

## Evaluation and rankings
Official judging score = 35 category performance + 15 priority performance + 20 functionality + 15 robustness + 10 technical explanation + 5 originality/responsible AI. Within each track teams are ranked separately.

Announcement adds: "Judging evaluates correct AI implementation, performance, clarity, responsible use, and team contribution—not just a polished interface."
