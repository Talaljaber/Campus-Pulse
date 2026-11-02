-- P9.2: at most two SLA reminders per clock period (PLAN (d) rows 16 and 16b).
-- 0 = none sent, 1 = first reminder (office), 2 = second and last (office + admin). A clock restart
-- resets it to 0 in application code.
alter table public.tickets
  add column reminder_count smallint not null default 0 check (reminder_count between 0 and 2);
