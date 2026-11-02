-- 05_announcements: two fictional announcements for the demo Home page (P9.5).
-- Requires migration 0013 (table public.announcements). Idempotent: fixed ids.
-- Fictional text only; created_by stays null (no real or seeded account is referenced).

insert into public.announcements (id, office, kind, title, body, starts_at, ends_at) values
('a0000000-0000-4000-8000-000000000501', 'it', 'outage',
 'Library wifi is down',
 'The wifi in the library is down and our team is working on it. Please use the lab network meanwhile. شبكة الواي فاي في المكتبة متوقفة حاليا، والفريق يعمل على إصلاحها.',
 now(), now() + interval '7 days'),
('a0000000-0000-4000-8000-000000000502', 'it', 'maintenance',
 'Outlook unavailable for two hours',
 'Outlook will be unavailable for two hours tonight during planned maintenance. البريد الإلكتروني لن يكون متاحا لمدة ساعتين الليلة بسبب صيانة مجدولة.',
 now(), now() + interval '2 days')
on conflict (id) do update set
  office = excluded.office, kind = excluded.kind, title = excluded.title, body = excluded.body,
  starts_at = excluded.starts_at, ends_at = excluded.ends_at, archived_at = null;
