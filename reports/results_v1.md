# CampusPulse v1: first results (ML batch 3)

Artifact `v1` sha `8fb011621fb6`, generated 2026-10-31T16:32:40+00:00 by `python scripts/results_v1.py`. This previews P2.8 (`evaluate.py`). Stage B is still provisional (equal ensemble weights, C at the grid midpoint). Encoder: int8 e5-small, vocabulary-pruned (identical embeddings).

**Protocol.** Only two kinds of numbers appear here: scenario-held-out OOF over the frozen `cv_fold` folds (LD-31), and the frozen model on our own test set. No random split is used anywhere. Groups are `cv_group` for OOF and `scenario_family` for our_test.

## Headline

| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| OOF, official rows | 432 | 30 | 0.490 | 0.512 | 0.904 | 0.903 | 0.440 |
| our_test set1 | 60 | 6 | 0.592 | 0.700 | 1.000 | 1.000 | 0.700 |
| our_test set2 | 72 | 16 | 0.746 | 0.750 | 0.782 | 0.778 | 0.611 |
| our_test set3 | 72 | 16 | 0.663 | 0.653 | 0.783 | 0.778 | 0.542 |
| our_test pooled | 204 | 38 | 0.710 | 0.701 | 0.847 | 0.843 | 0.613 |

Conformal sets on our_test (target coverage 90 %, α = 0.10 per target):

| set | cat coverage | cat mean size | pri coverage | pri mean size | ASK proxy (a set of size 2) |
| --- | ---: | ---: | ---: | ---: | ---: |
| set1 | 1.000 | 2.75 | 1.000 | 1.00 | 0.183 |
| set2 | 0.931 | 3.22 | 0.778 | 1.00 | 0.278 |
| set3 | 0.986 | 3.06 | 0.778 | 1.00 | 0.167 |
| pooled | 0.971 | 3.02 | 0.843 | 1.00 | 0.211 |

## Findings

- **Category is the weak target.** OOF category macro-F1 is 0.490 (M2-LR alone 0.594, M1 0.205, kNN 0.398). With one group per category held out, each fold learns a category from about 4 scenarios, and TF-IDF does not transfer to unseen scenarios at all. More scenarios (P2 augmentation) are the main lever; tuned weights (P2.7) are the second.
- **Arabic lags English.** OOF category macro-F1: ar 0.270 vs en 0.573; our_test: ar 0.522 vs en 0.796. A held-out Arabic scenario is usually held out with its English translation (same cv_group), so the Arabic side has the fewest same-language examples.
- **Category errors cluster on one label.** Top confusions (gold → predicted): Academic Support → Registration (17), Finance → Registration (16), Transportation → Facilities (7). 55 of 61 category errors still have the gold label inside the conformal set, so the ask/LLM path (P3) has the right candidates.
- **Priority sets never widen.** Mean priority set size on our_test is 1.00 and coverage 0.843 (target 0.90); 0 of 32 priority errors have the gold label in the set. The head is calibrated on OOF data where the lexicon features separate priority almost perfectly, so it is over-confident on new phrasing. Top confusions: low → medium (17), high → medium (10), medium → high (4). P2 recalibration must fix this (e.g. calibrate on augmented scenarios, or `alpha_priority_fallback`).
- **Arabizi priority is weak** (macro-F1 0.301 on 32 rows): no Arabizi was trained on yet (the P1.9 rows await the human check).
- **The head is what makes priority work:** OOF priority macro-F1 0.578 for the members' average, 0.860 after the head, 0.904 with the safety floor.

## OOF (scenario-held-out) by language

Official rows; `lang` is script-only (there is no Arabizi in the official data).

| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ar | 135 | 15 | 0.270 | 0.333 | 0.922 | 0.933 | 0.267 |
| en | 297 | 27 | 0.573 | 0.593 | 0.893 | 0.889 | 0.518 |
| all pool rows | 432 | 30 | 0.490 | 0.512 | 0.904 | 0.903 | 0.440 |

## Per model

OOF, official rows:

| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 432 | 30 | 0.490 | 0.512 | 0.904 | 0.903 | 0.440 |
| M1 (TF-IDF LR) | 432 | 30 | 0.205 | 0.215 | 0.542 | 0.537 | 0.076 |
| M2-LR (e5 + LR) | 432 | 30 | 0.594 | 0.604 | 0.589 | 0.583 | 0.326 |
| M2-kNN | 432 | 30 | 0.398 | 0.394 | 0.337 | 0.368 | 0.102 |

Priority stages (OOF, official rows): members_average: macro-F1 0.578, acc 0.562; head: macro-F1 0.860, acc 0.857; head_plus_safety_floor: macro-F1 0.904, acc 0.903.

our_test pooled (member argmax; a member's priority is before the head and floors):

| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ensemble (tier 0) | 204 | 38 | 0.710 | 0.701 | 0.847 | 0.843 | 0.613 |
| M1 (TF-IDF LR) | 204 | 38 | 0.559 | 0.574 | 0.576 | 0.588 | 0.284 |
| M2-LR (e5 + LR) | 204 | 38 | 0.689 | 0.696 | 0.665 | 0.662 | 0.466 |
| M2-kNN | 204 | 38 | 0.498 | 0.515 | 0.297 | 0.328 | 0.157 |

## our_test by language (pooled)

| slice | rows | groups | cat macro-F1 | cat acc | pri macro-F1 | pri acc | joint acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| en | 97 | 15 | 0.796 | 0.804 | 0.874 | 0.876 | 0.753 |
| ar | 75 | 15 | 0.522 | 0.520 | 0.585 | 0.853 | 0.413 |
| arabizi | 32 | 8 | 0.696 | 0.812 | 0.301 | 0.719 | 0.656 |

## Errors on our_test (79 of 204 rows)

| id | set | lang | text | gold | pred | wrong | size S_cat | size S_pri |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| HT-0002 | set1 | ar | بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0004 | set1 | ar | ارجو المساعدة، وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0008 | set1 | ar | عندي مشكلة: بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0009 | set1 | ar | مرحبا يا جماعة وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0019 | set1 | ar | وين مكتب المرشد الاكاديمي؟ وشكرا | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0021 | set1 | ar | وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0024 | set1 | ar | سؤال: وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0025 | set1 | ar | مرحبا، وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0026 | set1 | ar | سؤال: بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0028 | set1 | ar | لو سمحت بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0031 | set1 | ar | عندي مشكلة: وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0039 | set1 | ar | ممكن تساعدوني؟ بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0040 | set1 | ar | بدي نسخة من وصل الدفع وشكرا | Finance / low | Registration / low | category | 3 | 1 |
| HT-0044 | set1 | ar | ممكن تساعدوني؟ وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0047 | set1 | ar | مرحبا يا جماعة بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0052 | set1 | ar | لو سمحت وين مكتب المرشد الاكاديمي؟ | Academic Support / low | Registration / low | category | 5 | 1 |
| HT-0058 | set1 | ar | ارجو المساعدة، بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| HT-0060 | set1 | ar | مرحبا، بدي نسخة من وصل الدفع | Finance / low | Registration / low | category | 3 | 1 |
| T2-0002 | set2 | en | The registration portal shows the wrong number of credit hours for me Please respond when possible. | Registration / medium | Finance / medium | category | 2 | 1 |
| T2-0004 | set2 | en | I cannot log in to submit my project and the submission closes in one hour Please respond when possible. | IT Support / high | Registration / high | category | 3 | 1 |
| T2-0007 | set2 | ar | ارجو المساعدة، السواق ما وقف بموقف الباص اليوم الصبح | Transportation / medium | Transportation / high | priority | 4 | 1 |
| T2-0008 | set2 | ar | ممكن تساعدوني؟ الحنفية بحمام الطابق الثاني بتنقط | Facilities / low | Facilities / medium | priority | 5 | 1 |
| T2-0012 | set2 | en | URGENT: The registration portal shows the wrong number of credit hours for me | Registration / medium | Finance / medium | category | 2 | 1 |
| T2-0017 | set2 | ar | السواق ما وقف بموقف الباص اليوم الصبح | Transportation / medium | Transportation / high | priority | 4 | 1 |
| T2-0018 | set2 | en | The shuttle broke down on the highway and students are stuck there Please respond when possible. | Transportation / high | Facilities / medium | category, priority | 2 | 1 |
| T2-0027 | set2 | arabizi | fi bas lal jam3a yom el jum3a? w shukran | Transportation / low | IT Support / medium | category, priority | 4 | 1 |
| T2-0028 | set2 | en | URGENT: The shuttle broke down on the highway and students are stuck there | Transportation / high | Facilities / medium | category, priority | 2 | 1 |
| T2-0031 | set2 | ar | سؤال: علامة الميد ترم مش منزلة صح على النظام | Academic Support / medium | Registration / medium | category | 3 | 1 |
| T2-0035 | set2 | en | Student request: I cannot log in to submit my project and the submission closes in one hour | IT Support / high | Registration / high | category | 3 | 1 |
| T2-0037 | set2 | arabizi | fi bas lal jam3a yom el jum3a? | Transportation / low | Transportation / medium | priority | 4 | 1 |
| T2-0038 | set2 | ar | مرحبا، السواق ما وقف بموقف الباص اليوم الصبح | Transportation / medium | Transportation / high | priority | 4 | 1 |
| T2-0039 | set2 | ar | الحنفية بحمام الطابق الثاني بتنقط وشكرا | Facilities / low | Facilities / medium | priority | 5 | 1 |
| T2-0041 | set2 | ar | علامة الميد ترم مش منزلة صح على النظام | Academic Support / medium | Registration / medium | category | 3 | 1 |
| T2-0043 | set2 | en | Hi team, The registration portal shows the wrong number of credit hours for me | Registration / medium | Finance / medium | category | 2 | 1 |
| T2-0045 | set2 | en | I cannot log in to submit my project and the submission closes in one hour | IT Support / high | Registration / high | category | 3 | 1 |
| T2-0048 | set2 | ar | مرحبا يا جماعة السواق ما وقف بموقف الباص اليوم الصبح | Transportation / medium | Transportation / high | priority | 4 | 1 |
| T2-0049 | set2 | ar | الحنفية بحمام الطابق الثاني بتنقط | Facilities / low | Facilities / medium | priority | 5 | 1 |
| T2-0053 | set2 | en | The registration portal shows the wrong number of credit hours for me | Registration / medium | Finance / medium | category | 2 | 1 |
| T2-0058 | set2 | arabizi | URGENT: fi bas lal jam3a yom el jum3a? | Transportation / low | Transportation / medium | priority | 4 | 1 |
| T2-0059 | set2 | en | Hi team, The shuttle broke down on the highway and students are stuck there | Transportation / high | Facilities / medium | category, priority | 2 | 1 |
| T2-0062 | set2 | ar | عندي مشكلة: علامة الميد ترم مش منزلة صح على النظام | Academic Support / medium | Registration / medium | category | 3 | 1 |
| T2-0066 | set2 | en | This is my issue: I cannot log in to submit my project and the submission closes in one hour | IT Support / high | Registration / high | category | 3 | 1 |
| T2-0068 | set2 | arabizi | 3indi moshkle: fi bas lal jam3a yom el jum3a? | Transportation / low | Academic Support / medium | category, priority | 3 | 1 |
| T2-0069 | set2 | en | The shuttle broke down on the highway and students are stuck there | Transportation / high | Facilities / medium | category, priority | 2 | 1 |
| T2-0070 | set2 | ar | مرحبا يا جماعة الحنفية بحمام الطابق الثاني بتنقط | Facilities / low | Facilities / medium | priority | 5 | 1 |
| T2-0072 | set2 | ar | مرحبا، علامة الميد ترم مش منزلة صح على النظام | Academic Support / medium | Registration / medium | category | 3 | 1 |
| T3-0001 | set3 | en | hey what's the max credit hours i can register this semester? | Registration / low | Finance / medium | category, priority | 4 | 1 |
| T3-0005 | set3 | en | I got charged a lab fee but my course has no lab | Finance / medium | Registration / medium | category | 5 | 1 |
| T3-0006 | set3 | arabizi | plz 7ello el hold el mali, dafa3t mbare7 w 3indi emti7an el yom | Finance / high | Registration / high | category | 4 | 1 |
| T3-0007 | set3 | ar | التكييف بالباص مش شغال والطلاب تعبانين من الحر | Transportation / medium | Facilities / medium | category | 2 | 1 |
| T3-0010 | set3 | ar | لو سمحت شو الخطوات لطلب توصية اكاديمية | Academic Support / low | Registration / low | category | 4 | 1 |
| T3-0011 | set3 | arabizi | plz ana bel tawari2 w el final hala2, shu a3mel? | Academic Support / high | Registration / medium | category, priority | 4 | 1 |
| T3-0014 | set3 | ar | الاوتلوك تبع الجامعة واقف، ما في ولا ايميل جديد من مبارح | IT Support / medium | Transportation / medium | category | 4 | 1 |
| T3-0015 | set3 | ar | بدي اعرف سياسة استرجاع الرسوم للمواد المسحوبة | Finance / low | Registration / low | category | 4 | 1 |
| T3-0016 | set3 | arabizi | ma khalooni adkhol el emti7an el yom 3shan el dafe3 mesh mbayyen, w ana dafe3!! | Finance / high | Registration / high | category | 4 | 1 |
| T3-0017 | set3 | ar | المكيف بالباص خربان والجو حر كثير | Transportation / medium | Facilities / medium | category | 2 | 1 |
| T3-0018 | set3 | arabizi | el bus da3am sayyara w e7na 3al autostrad, shu ne3mal? | Transportation / high | Transportation / medium | priority | 1 | 1 |
| T3-0020 | set3 | ar | بدي رسالة توصية للماجستير، شو الطريقة؟ | Academic Support / low | Registration / medium | category, priority | 4 | 1 |
| T3-0022 | set3 | en | I want to overload next semester, how many hours max? | Registration / low | IT Support / medium | category, priority | 3 | 1 |
| T3-0025 | set3 | ar | اذا سحبت مادة بترجعلي مصاريها؟ | Finance / low | Registration / medium | category, priority | 3 | 1 |
| T3-0028 | set3 | arabizi | sar 7adeth lal bas tabe3 el jam3a, ma 7ada mjarra7 bas e7na wa2fin 3al share3 | Transportation / high | Transportation / medium | priority | 4 | 1 |
| T3-0029 | set3 | ar | نص الكراسي بالقاعة 112 مكسورة والطلاب واقفين | Facilities / medium | Registration / medium | category | 3 | 1 |
| T3-0030 | set3 | en | please send someone now, a socket in the library is smoking | Facilities / high | Facilities / medium | priority | 1 | 1 |
| T3-0032 | set3 | en | Can I take more than 18 credit hours if my GPA is high? Who approves that? | Registration / low | Academic Support / low | category | 2 | 1 |
| T3-0034 | set3 | en | Hi, I'd like to install MATLAB on my laptop using the uni license, what are the steps? | IT Support / low | IT Support / medium | priority | 3 | 1 |
| T3-0037 | set3 | en | does the uni bus go to Zarqa? | Transportation / low | Transportation / medium | priority | 1 | 1 |
| T3-0039 | set3 | en | hey where can I pray on campus between lectures | Facilities / low | Academic Support / low | category | 3 | 1 |
| T3-0043 | set3 | ar | الشعبة مليانة وزر الانتظار مش راضي يشتغل، شو اعمل؟ | Registration / medium | Facilities / medium | category | 3 | 1 |
| T3-0046 | set3 | ar | لو سمحتو، بسترد فلوس المادة اذا سحبتها؟ | Finance / low | Registration / medium | category, priority | 5 | 1 |
| T3-0051 | set3 | ar | مين بقدر اطلب منه رسالة توصية وكم بتاخذ وقت؟ | Academic Support / low | Registration / low | category | 3 | 1 |
| T3-0056 | set3 | ar | شو نسبة الاسترداد اذا انسحبت من مادة بعد الاسبوع الاول؟ | Finance / low | Registration / low | category | 5 | 1 |
| T3-0059 | set3 | arabizi | accident lal bus 3and el dawwar, plz ib3atolna bas tani | Transportation / high | Transportation / medium | priority | 2 | 1 |
| T3-0060 | set3 | ar | الكراسي بقاعة المحاضرات مكسرة وما في مكان نقعد | Facilities / medium | Registration / medium | category | 4 | 1 |
| T3-0061 | set3 | ar | كيف بطلب رسالة توصية من دكتور؟ | Academic Support / low | IT Support / low | category | 3 | 1 |
| T3-0062 | set3 | en | Hi, is there another way to reach my advisor? no response since two weeks | Academic Support / medium | Academic Support / low | priority | 2 | 1 |
| T3-0063 | set3 | en | quick question about the credit hour limit, is 21 hours allowed for seniors | Registration / low | Finance / medium | category, priority | 4 | 1 |
| T3-0068 | set3 | en | Is there a GJU shuttle from Zarqa or only from Amman? | Transportation / low | Facilities / low | category | 3 | 1 |
| T3-0069 | set3 | arabizi | el bas 3emel 7adeth 3al taree2 w fi tollab ma3na | Transportation / high | Registration / medium | category, priority | 4 | 1 |
| T3-0070 | set3 | en | could someone tell me where the closest prayer room to the library is | Facilities / low | Facilities / medium | priority | 3 | 1 |

## Caveats (read before quoting any number)

- **Thin data, wide error bars (LD-32).** The 432 official rows are 42 distinct texts in 30 scenario groups
  (9 to 11 wrapper variants each). Each OOF fold holds out one group per category, so each category is learned
  from about 4 groups. The effective sample size is about 30 groups, not 432 rows: read every OOF number as
  roughly plus or minus 0.1, and treat no difference between models here as significant.
- **Conformal coverage is approximate.** The quantiles are calibrated on the OOF scores of those same 30
  groups, so the 90 % guarantee holds only loosely, and OOF coverage is in-sample for the quantile.
- **set1 is not unseen scenarios.** It restates 6 training scenarios in the other language, so it measures
  cross-lingual transfer and is easier than the hidden test.
- **Sets 2 and 3 were written by an LLM (D-010).** Their scenarios are unseen, but their phrasing and labels
  follow `docs/reference/label_decisions.md` as an LLM read it, not the organizers' labeller.
- **The "today" shortcut (LD-34).** In the official data every row with "today"/"اليوم" is high and no other
  row is. The `deadline_today` feature and the head learn that, so priority scores on data with the same cue
  are optimistic. The P2.5 probes break the shortcut and P2.9 masks it.
- **The priority lexicons were written after reading every official row.** The evidence patterns
  (`urgency.yaml`) and the danger lexicon (`safety.yaml`) were seeded from the official cores of all folds,
  so OOF priority is not fully held out from the lexicons. our_test sets 2 and 3 are the cleaner check.
- **Provisional configuration.** Equal ensemble weights and mid-grid C; P2.7 tunes both on OOF only. With
  equal weights the weak M1 member pulls the ensemble's category score below M2-LR alone.
- **No augmentation yet.** The 30 Arabizi rule rows await the human check (P1.9), so no Arabizi was trained
  on; Arabizi results rely on the transliteration and the Arabizi lexicon patterns.
