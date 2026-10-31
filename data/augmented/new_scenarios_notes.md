# new_scenarios.csv: label notes for review

One line per new situation (P2.3). Each situation has 5 rows in `new_scenarios.csv` (en, ar, arabizi, en paraphrase, ar paraphrase) sharing its labels and `cv_group`. Rules are from `docs/reference/label_decisions.md`: topic beats channel; low = information request or ambient fixture; medium = concrete malfunction with a workaround (teaching-room equipment is medium); high = deadline within hours, exam happening now, safety risk, students stranded, or a definitive loss/blocking of enrolment. Sub-topics marked ('today' in a low) etc. carry time words on purpose, so the model does not learn "today = high".

| id | category | priority | rule that decided the priority | sub-topic |
| --- | --- | --- | --- | --- |
| NEW-C01 | Finance | low | low: information request (where/how/copy of/advice) | payment methods: eFAWATEERcom how-to ('today' in a low) |
| NEW-C02 | Finance | low | low: information request (where/how/copy of/advice) | sibling discount (eligibility info) |
| NEW-C03 | Finance | low | low: information request (where/how/copy of/advice) | statements: stamped account statement for German Year visa |
| NEW-C04 | Finance | low | low: information request (where/how/copy of/advice) | refund policy after a late course withdrawal |
| NEW-C05 | Finance | low | low: information request (where/how/copy of/advice) | sponsor/employer payment procedure ('next month') |
| NEW-C06 | Finance | low | low: information request (where/how/copy of/advice) | loans and fee deferral options |
| NEW-C07 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | double charge for one installment |
| NEW-C08 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | employee-children discount not applied |
| NEW-C09 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | late-payment fine applied wrongly |
| NEW-C10 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | card payment declined on the fees page (topic beats channel) |
| NEW-C11 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | lab fee still billed for a dropped course |
| NEW-C12 | Finance | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | refund after semester withdrawal is late ('last month') |
| NEW-C13 | Finance | high | high: exam/defence happening now | financial hold blocking a final exam that starts in 30 minutes |
| NEW-C14 | Finance | high | high: definitive loss/blocking of enrolment | employer/sponsor payment not matched, enrolment cancelled |
| NEW-C15 | Finance | high | high: deadline within hours | installment bill missing on eFAWATEERcom, payment window closes at 2 pm |
| NEW-C16 | Finance | high | high: deadline within hours | graduation financial clearance blocked, list closes at noon |
| NEW-C17 | Finance | high | high: deadline within hours | fees-paid letter needed for a residence-permit appointment this afternoon |
| NEW-C18 | Finance | high | high: definitive loss/blocking of enrolment | pending fee deferral ignored, withdrawn from the semester for non-payment |
| NEW-C19 | Registration | low | low: information request (where/how/copy of/advice) | credit-hour cap per semester |
| NEW-C20 | Registration | low | low: information request (where/how/copy of/advice) | procedure to withdraw from one course mid-semester |
| NEW-C21 | Registration | low | low: information request (where/how/copy of/advice) | waiting list for a full section |
| NEW-C22 | Registration | low | low: information request (where/how/copy of/advice) | registering the field-training course |
| NEW-C23 | Registration | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | placed in the wrong section |
| NEW-C24 | Registration | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | duplicated course entry inflating credit hours |
| NEW-C25 | Registration | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | drop confirmed but course still registered ('last week') |
| NEW-C26 | Registration | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | approved overload not applied ('next week' deadline is not urgent) |
| NEW-C27 | Registration | high | high: definitive loss/blocking of enrolment | enrolment status switched to 'withdrawn' without a request |
| NEW-C28 | Registration | high | high: deadline within hours | advisor-approval hold blocks late registration closing within the hour |
| NEW-C29 | Registration | high | high: definitive loss/blocking of enrolment | only section of the last required course cancelled, graduation blocked |
| NEW-C30 | Registration | high | high: deadline within hours | accidental withdrawal reversible only until 3 pm |
| NEW-C31 | IT Support | low | low: information request (where/how/copy of/advice) | university email setup on a phone |
| NEW-C32 | IT Support | low | low: information request (where/how/copy of/advice) | student software licences (Office, MATLAB) |
| NEW-C33 | IT Support | low | low: information request (where/how/copy of/advice) | remote access/VPN for library databases |
| NEW-C34 | IT Support | low | low: information request (where/how/copy of/advice) | restoring deleted cloud files ('last week' in a low) |
| NEW-C35 | IT Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | lab PCs reject one student's login (profile error) |
| NEW-C36 | IT Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | university mailbox not receiving ('since yesterday') |
| NEW-C37 | IT Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | two-factor codes not arriving (backup codes as workaround) |
| NEW-C38 | IT Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | virtual-lecture link gives 'access denied' (joins via a friend) |
| NEW-C39 | IT Support | high | high: deadline within hours | hacked account sending spam, locked out before a midnight submission |
| NEW-C40 | IT Support | high | high: deadline within hours | submission system server error, window closes in 40 minutes |
| NEW-C41 | IT Support | high | high: exam/defence happening now | lab-wide network outage during a live practical exam |
| NEW-C42 | IT Support | high | high: exam/defence happening now | video platform dropping a live online thesis defence |
| NEW-C43 | Transportation | low | low: information request (where/how/copy of/advice) | bus subscription sign-up and price |
| NEW-C44 | Transportation | low | low: information request (where/how/copy of/advice) | route coverage (is there a Zarqa line) |
| NEW-C45 | Transportation | low | low: information request (where/how/copy of/advice) | pickup point location ('tomorrow' in a low) |
| NEW-C46 | Transportation | low | low: information request (where/how/copy of/advice) | lost and found on the bus ('yesterday' in a low) |
| NEW-C47 | Transportation | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | driver skips a stop |
| NEW-C48 | Transportation | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | bus air conditioning broken (vehicle comfort, not a room) |
| NEW-C49 | Transportation | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | paid subscriber missing from the driver's passenger list |
| NEW-C50 | Transportation | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | bus departs early ('today' in a medium) |
| NEW-C51 | Transportation | high | high: students stranded (and unsafe) | bus breakdown on a highway shoulder, no replacement |
| NEW-C52 | Transportation | high | high: safety risk | driver texting and speeding right now |
| NEW-C53 | Transportation | high | high: students stranded (and unsafe) | dropped at the wrong stop at night with no transport |
| NEW-C54 | Transportation | high | high: safety risk | smoke from the bus engine while moving |
| NEW-C55 | Facilities | low | low: information request (where/how/copy of/advice) | booking a library group-study room |
| NEW-C56 | Facilities | low | low: ambient fixture, no teaching-room impact | stopped clock at the cafeteria entrance (ambient fixture) |
| NEW-C57 | Facilities | low | low: information request (where/how/copy of/advice) | how to report maintenance after hours |
| NEW-C58 | Facilities | low | low: information request (where/how/copy of/advice) | student lockers |
| NEW-C59 | Facilities | medium | medium: teaching-room equipment/building fault with a workaround | dead power sockets in a teaching lab |
| NEW-C60 | Facilities | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | no water in one floor's bathrooms ('this morning'/'today' in a medium) |
| NEW-C61 | Facilities | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | elevator out of service (stairs as workaround) |
| NEW-C62 | Facilities | medium | medium: teaching-room equipment/building fault with a workaround | broken chairs and desks in a lecture hall |
| NEW-C63 | Facilities | high | high: safety risk | gas smell in the chemistry lab |
| NEW-C64 | Facilities | high | high: safety risk | sparks and smoke from an electrical panel |
| NEW-C65 | Facilities | high | high: safety risk | ceiling panel fell during class |
| NEW-C66 | Facilities | high | high: safety risk | fallen tree branch and hanging power cable on a walkway |
| NEW-C67 | Academic Support | low | low: information request (where/how/copy of/advice) | how the cumulative GPA and repeats are calculated |
| NEW-C68 | Academic Support | low | low: information request (where/how/copy of/advice) | German Year eligibility requirements |
| NEW-C69 | Academic Support | low | low: information request (where/how/copy of/advice) | tutoring / help sessions for a course |
| NEW-C70 | Academic Support | low | low: information request (where/how/copy of/advice) | attendance limit before exam deprivation |
| NEW-C71 | Academic Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | midterm grade missing for one student |
| NEW-C72 | Academic Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | final-exam schedule lists a room that does not exist |
| NEW-C73 | Academic Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | advisor not responding to a study-plan approval ('two weeks') |
| NEW-C74 | Academic Support | medium | medium: concrete malfunction/service issue with a workaround, no immediate severe impact | wrongly recorded absences |
| NEW-C75 | Academic Support | high | high: exam/defence happening now | barred from a final starting in 45 minutes despite a medical excuse |
| NEW-C76 | Academic Support | high | high: deadline within hours | make-up exam request due by 2 pm after a hospital stay |
| NEW-C77 | Academic Support | high | high: definitive loss/blocking of enrolment | academic dismissal although an approved grade change lifts the GPA |
| NEW-C78 | Academic Support | high | high: deadline within hours | thesis due within the hour, supervisor signature missing |

## Borderline calls (check these first)

- NEW-C10 (card declined on the fees page): Finance, not IT Support. Topic beats channel: the problem is paying a fee, and the account and platform otherwise work.
- NEW-C06 ("I'm struggling to cover this semester's fees"): low. It asks which options exist and how to apply. Nothing has broken and no deadline is given.
- NEW-C17 (fees-paid letter for a residence permit): high only because the appointment is this afternoon. Without the deadline it would be a "copy of" request (low).
- NEW-C18 (Finance) vs NEW-C27 (Registration): both students were withdrawn from the semester. The stated cause (non-payment) makes C18 Finance. C27 gives no finance cause, so it is Registration.
- NEW-C28 (advisor-approval hold blocks late registration): Registration, not Academic Support. The request is about being unable to register, and the advisor is only the reason.
- NEW-C26 (approved overload not applied, "add/drop ends next week"): medium. The deadline is days away.
- NEW-C39 (hacked account): high because of the midnight submission deadline the student is locked out of. The security incident alone was not used as the high signal.
- NEW-C40 (submission system "server error", closes in 40 minutes): IT Support high. It mirrors the official medium upload-error scenario but adds a deadline within the hour.
- NEW-C34 (restoring deleted OneDrive files): low. It is a how-to question, not a malfunction.
- NEW-C48 (bus air conditioning): Transportation. The vehicle is the topic, not a room (compare the official Facilities AC scenario).
- NEW-C59 (dead sockets in the computer lab): Facilities medium (room infrastructure), not IT Support.
- NEW-C61 (elevator out of service): medium with stairs as the workaround. It was written without a mobility-impaired student so that it stays unambiguous.
- NEW-C56 (stopped clock at the cafeteria entrance): low, as an ambient fixture under the hallway-light rule.
- NEW-C72 (final-exam room that does not exist): Academic Support (the exam schedule), not Facilities.
