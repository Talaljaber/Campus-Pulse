-- 03_advisor_slots: 30-minute slots for every seeded advisor over the next 14 days, inside
-- office hours (Sun–Thu 09:00–15:00 Asia/Amman). Fallback calendar when Google is off (P4.3).
-- Idempotent: existing (advisor, start) pairs, booked or not, are left untouched; re-running
-- later only adds the newly in-range days.

insert into public.advisor_slots (advisor_id, starts_at, ends_at)
select a.id,
       (d.day + time '09:00' + s.n * interval '30 minutes') at time zone 'Asia/Amman',
       (d.day + time '09:00' + (s.n + 1) * interval '30 minutes') at time zone 'Asia/Amman'
from public.advisors a
cross join lateral (
  select (now() at time zone 'Asia/Amman')::date + i as day from generate_series(0, 13) as i
) d
cross join generate_series(0, 11) as s(n)                 -- 09:00 .. 14:30 starts
where extract(isodow from d.day) in (7, 1, 2, 3, 4)       -- Sunday..Thursday
  and a.id::text like 'a0000000-0000-4000-8000-%'         -- seeded advisors only
on conflict (advisor_id, starts_at) do nothing;
