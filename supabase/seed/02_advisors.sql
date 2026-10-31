-- 02_advisors: six FICTIONAL advisors (P4.3). Names are invented; every demo_email is a
-- plus-address of the project's own demo inbox and must be in DEMO_EMAIL_ALLOWLIST
-- (checked by scripts/check_seed_contacts.py). department = the routing office code.
-- Office hours: Sun–Thu 09:00–15:00 Asia/Amman (weekday numbers are Monday = 0).
-- Idempotent: fixed ids, re-running updates in place.

insert into public.advisors (id, fictional_name, department, room, calendar_id, demo_email, office_hours) values
  ('a0000000-0000-4000-8000-000000000001', 'Dr. Rana Haddad (fictional)',   'academic',  'C-210', null,
   'campuspulse.support+adv-academic1@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}'),
  ('a0000000-0000-4000-8000-000000000002', 'Dr. Omar Khalil (fictional)',   'academic',  'E-105', null,
   'campuspulse.support+adv-academic2@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}'),
  ('a0000000-0000-4000-8000-000000000003', 'Dr. Lina Saleh (fictional)',    'academic',  'B-302', null,
   'campuspulse.support+adv-academic3@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}'),
  ('a0000000-0000-4000-8000-000000000004', 'Dr. Yazan Nasser (fictional)',  'academic',  'D-118', null,
   'campuspulse.support+adv-academic4@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}'),
  ('a0000000-0000-4000-8000-000000000005', 'Ms. Dana Aziz (fictional)',     'registrar', 'F-012', null,
   'campuspulse.support+adv-reg1@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}'),
  ('a0000000-0000-4000-8000-000000000006', 'Mr. Sami Barakat (fictional)',  'registrar', 'F-014', null,
   'campuspulse.support+adv-reg2@gmail.com',
   '{"tz": "Asia/Amman", "weekdays": [6, 0, 1, 2, 3], "start": "09:00", "end": "15:00"}')
on conflict (id) do update set
  fictional_name = excluded.fictional_name, department = excluded.department, room = excluded.room,
  calendar_id = excluded.calendar_id, demo_email = excluded.demo_email, office_hours = excluded.office_hours;
