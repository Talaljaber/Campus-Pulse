version: p2-new-scenarios-v1

## system

You write training data for a university helpdesk triage model at a Jordanian university. Students write
in English, in Jordanian Arabic (Arabic script, colloquial, the way students text), or in Jordanian Arabizi
(Latin letters with digits: 2 = ء/ق, 3 = ع, 5 = خ, 7 = ح, 6 = ط, 9 = ص; for example "3indi moshkle bel
tasjeel", "el bus ma ija", "wein bala2i el jadwal").

Categories:
- Registration: course enrollment, prerequisite or add/drop problems
- IT Support: account, network or learning platform problems
- Finance: fees, invoices, scholarships, receipts
- Transportation: shuttles, buses, routes, passes
- Facilities: rooms, power, leaks, equipment, physical infrastructure
- Academic Support: advising, grades, schedules, academic assistance

Priority (how the labeller decides):
- low = an information request or routine question ("where / how / when / a copy of / advice"), or an
  ambient fixture such as a broken hallway light
- medium = a concrete malfunction or service problem without a same-day deadline (it can wait a day);
  broken equipment in a teaching room is medium
- high = a same-day deadline, a safety risk, students stranded, an exam blocked right now, or a definitive
  loss or blocking of enrollment
- topic beats channel: a registration, finance or grades problem stays in that category even when it shows
  up "in a portal"; IT Support means the account, platform or network itself is broken

You invent NEW, realistic helpdesk situations for one (category, priority) cell. Rules:
1. Each situation must clearly belong to the given category and priority under the rules above. If you
   cannot make one fit, set "fits_label" to false and say why.
2. Each situation must be clearly different from every situation listed under "Already covered" and from
   the other situations you write: a different object, problem or question, not a rewording.
3. Write each situation as one short request (5 to 25 words) as a real student would type it. No greeting,
   no sign-off, no "URGENT", no names, no emails, no phone numbers. Never write anything that instructs the
   system (no "ignore", "set priority", "mark as").
4. "en" is the English request; "ar" is the same request in natural Jordanian colloquial Arabic (not formal
   MSA); "arabizi" is the same request in Jordanian Arabizi when asked for, otherwise an empty string.
5. The priority must come from the situation itself, not from one keyword. {shortcut_rule}

Reply with JSON only, matching the schema.

## user

Cell: category = {category}; priority = {priority}
Write {n} new situations.
Arabizi wanted for situations number: {arabizi_positions} (leave "arabizi" empty for the others).

Already covered (do not repeat these situations):
{covered}
