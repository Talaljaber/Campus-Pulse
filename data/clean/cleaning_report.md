# Cleaning report
Inputs: data/raw/train.csv (370 rows), data/raw/validation.csv (62 rows). UTF-8 BOM present: {'train.csv': True, 'validation.csv': True}. Read with utf-8-sig. Hidden test files were never accessed.
## Row and scenario counts
| split | lang | rows | scenarios |
|---|---|---|---|
| train | ar | 117 | 13 |
| train | en | 253 | 23 |
| val | ar | 18 | 2 |
| val | en | 44 | 4 |

Totals: train 370 rows / 36 scenarios; val 62 rows / 6 scenarios.
## Label distributions (rows)
### Category: train
| category | rows |
|---|---|
| IT Support | 62 |
| Finance | 62 |
| Facilities | 62 |
| Academic Support | 62 |
| Transportation | 62 |
| Registration | 60 |

### Priority: train
| priority | rows |
|---|---|
| medium | 137 |
| high | 131 |
| low | 102 |
### Category: val
| category | rows |
|---|---|
| Registration | 11 |
| Finance | 11 |
| Academic Support | 11 |
| IT Support | 11 |
| Transportation | 9 |
| Facilities | 9 |

### Priority: val
| priority | rows |
|---|---|
| medium | 29 |
| low | 22 |
| high | 11 |
### Category: combined
| category | rows |
|---|---|
| IT Support | 73 |
| Finance | 73 |
| Academic Support | 73 |
| Facilities | 71 |
| Registration | 71 |
| Transportation | 71 |

### Priority: combined
| priority | rows |
|---|---|
| medium | 166 |
| high | 142 |
| low | 124 |

### Category x priority: train
| category | high | low | medium |
|---|---|---|---|
| Academic Support | 9 | 22 | 31 |
| Facilities | 31 | 20 | 11 |
| Finance | 20 | 22 | 20 |
| IT Support | 31 | 9 | 22 |
| Registration | 31 | 9 | 20 |
| Transportation | 9 | 20 | 33 |

### Language x priority: train
| lang | high | low | medium |
|---|---|---|---|
| ar | 54 | 36 | 27 |
| en | 77 | 66 | 110 |

### Category x priority: val
| category | high | low | medium |
|---|---|---|---|
| Academic Support | 11 | 0 | 0 |
| Facilities | 0 | 0 | 9 |
| Finance | 0 | 0 | 11 |
| IT Support | 0 | 11 | 0 |
| Registration | 0 | 11 | 0 |
| Transportation | 0 | 0 | 9 |

### Language x priority: val
| lang | high | low | medium |
|---|---|---|---|
| ar | 0 | 0 | 18 |
| en | 11 | 22 | 11 |

### Scenario-level (unique scenarios) priority by language, combined
| lang | high | low | medium |
|---|---|---|---|
| ar | 6 | 4 | 5 |
| en | 8 | 8 | 11 |

## Prefixes and suffixes stripped
### Prefixes (train)
| prefix | rows |
|---|---|
| (none) | 72 |
| Hi team, | 23 |
| Student request: | 23 |
| Hello, | 23 |
| URGENT: | 23 |
| Please help: | 23 |
| I need assistance. | 23 |
| This is my issue: | 23 |
| Could you assist? | 23 |
| University helpdesk: | 23 |
| مرحبا يا جماعة | 13 |
| ارجو المساعدة، | 13 |
| لو سمحت | 13 |
| سؤال: | 13 |
| عندي مشكلة: | 13 |
| مرحبا، | 13 |
| ممكن تساعدوني؟ | 13 |

### Suffixes (train)
| suffix | rows |
|---|---|
| (none) | 334 |
| Please respond when possible. | 23 |
| وشكرا | 13 |
### Prefixes (val)
| prefix | rows |
|---|---|
| (none) | 12 |
| University helpdesk: | 4 |
| URGENT: | 4 |
| I need assistance. | 4 |
| Hi team, | 4 |
| Please help: | 4 |
| This is my issue: | 4 |
| Could you assist? | 4 |
| Student request: | 4 |
| Hello, | 4 |
| عندي مشكلة: | 2 |
| ارجو المساعدة، | 2 |
| مرحبا، | 2 |
| مرحبا يا جماعة | 2 |
| سؤال: | 2 |
| ممكن تساعدوني؟ | 2 |
| لو سمحت | 2 |

### Suffixes (val)
| suffix | rows |
|---|---|
| (none) | 56 |
| Please respond when possible. | 4 |
| وشكرا | 2 |

Data-driven detection (pooled): 16 prefixes, 2 suffixes; all contained in the hardcoded lists (asserted). Hardcoded entries never seen in data: none.
URGENT marker rows: train 23, val 4. Check: priority of URGENT rows vs others is determined by the scenario only (labels are consistent per scenario), so the marker carries no label signal.
## Sanity checks performed (all passed)
- row counts preserved (train 370, val 62)
- request_ids unique
- every row maps to a scenario
- every scenario has a single category and a single priority
- no empty core / text_norm
- no residual prefix (core starts with no known/detected prefix)
- no residual suffix (core ends with no known/detected suffix)
- labels identical to raw
- hardcoded wrapper lists cover all data-driven detections
- translated pairs have matching labels
- scenario counts 36 train / 6 val
- cv_group never splits a translated pair

## Cross-lingual translation pairs (manually verified)
| Arabic scenario | Arabic core | English scenario | English core | splits (ar/en) | labels ar | labels en | match |
|---|---|---|---|---|---|---|---|
| TR-S33 | الضو بالممر خربان | TR-S27 | A hallway light is broken | train/train (same split) | Facilities/low | Facilities/low | yes |
| TR-S35 | المبلغ الظاهر على حسابي مش صحيح | VA-S02 | The finance portal shows the wrong outstanding balance | train/val (LEAKAGE) | Finance/medium | Finance/medium | yes |
| TR-S01 | حسابي الجامعي تسكر وعندي امتحان اونلاين اليوم | TR-S32 | My university account is locked and I have an online exam today | train/train (same split) | IT Support/high | IT Support/high | yes |
| TR-S26 | دفعت القسط ولسه مش ظاهر بالدفع والتسجيل بسكر اليوم | TR-S07 | My tuition payment is not reflected and registration closes today | train/train (same split) | Finance/high | Finance/high | yes |
| TR-S05 | علامتي غلط وآخر يوم اعتراض اليوم | VA-S05 | My exam grade was recorded incorrectly and the appeal deadline is today | train/val (LEAKAGE) | Academic Support/high | Academic Support/high | yes |
| TR-S34 | عندي امتحانين بنفس الوقت | TR-S24 | The exam schedule has two tests at the same time | train/train (same split) | Academic Support/medium | Academic Support/medium | yes |
| TR-S29 | في مي بتسرب جنب كهربا المختبر | TR-S19 | Water is leaking near an electrical socket in the lab | train/train (same split) | Facilities/high | Facilities/high | yes |
| TR-S10 | كيف بغير كلمة السر؟ | VA-S06 | How can I reset my university password? | train/val (LEAKAGE) | IT Support/low | IT Support/low | yes |
| TR-S25 | مش قادر اسجل مواد والنظام بعطيني خطأ | TR-S21 | I cannot add my courses because the registration portal rejects my request | train/train (same split) | Registration/high | Registration/high | yes |
| TR-S08 | وين بلاقي مواعيد السحب والاضافة؟ | VA-S01 | Where can I find the add-drop period dates? | train/val (LEAKAGE) | Registration/low | Registration/low | yes |
| TR-S15 | وين جدول الباصات؟ | TR-S36 | Where can I see the shuttle bus timetable? | train/train (same split) | Transportation/low | Transportation/low | yes |
| VA-S03 | باص الجامعة اتأخر عن موعده | TR-S14 | The university bus is running twenty minutes late | val/train (LEAKAGE) | Transportation/medium | Transportation/medium | yes |

12 pairs; 5 cross-split pairs (translation leakage between train and val). Label mismatches: 0. Same-language exact core overlap across splits: none.

Scenarios with no translation counterpart: TR-S02 (I need a copy of my payment receipt); TR-S03 (A laboratory door is stuck and students cannot leave); TR-S04 (The system removed my registered course without warning); TR-S06 (I need help understanding the prerequisite rule); TR-S09 (Where can I meet my academic advisor?); TR-S11 (The learning platform is unavailable during an online quiz); TR-S12 (The student portal shows an error when I upload a file); TR-S13 (My scholarship discount is missing from the invoice); TR-S16 (The campus Wi-Fi disconnects every few minutes); TR-S17 (Where do I check the tuition installment dates?); TR-S18 (I cannot access the feedback on my assignment); TR-S20 (An air conditioner stopped working in the lecture room); TR-S22 (My bus pass stopped working this morning); TR-S23 (The bus route changed without an announcement); TR-S28 (I need advice choosing an elective course); TR-S30 (صفحة التسجيل معلقة عندي); TR-S31 (الباص الاخير انلغى وضلوا طلاب بدون مواصلات); VA-S04 (البروجكتور بالغرفة مش شغال)

cv_group in train_val_combined.csv = min(scenario_id, translation partner id) so a scenario and its translation share one group.

## Text oddities handled
- Rows whose suffix is glued to the core without punctuation: 34 (e.g. 'A hallway light is broken Please respond when possible.'); stripped by exact-suffix match.
- Rows with irregular whitespace (leading/trailing/double/NBSP) in raw text: 0.
- UTF-8 BOM at file start handled via utf-8-sig.
- Arabic cores keep a trailing question mark in `core`; it is removed only in `text_norm`.
- English prefixes ending in '.'/'?' ('I need assistance.', 'Could you assist?') are stripped as whole strings, so no stray punctuation remains.
- `text` is kept raw and unchanged.
