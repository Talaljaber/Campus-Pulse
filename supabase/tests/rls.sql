-- RLS proof (ARCHITECTURE §3.14, P4.1). Plain SQL, no pgTAP. Runs as postgres inside one
-- transaction that is rolled back, so fixtures never persist. Each check impersonates a
-- client by setting request.jwt.claims and `set local role`, exactly as PostgREST does.
-- Output: one row per check, then a summary row "RLS: n/13 checks passed".
-- Run: scripts/test_rls.py (local stack via psql), or paste into the SQL editor / MCP.
-- Fixture identities are fictional aliases; emails use the reserved example.invalid domain.

begin;

create temp table _rls (n int, name text, ok boolean, detail text) on commit drop;

-- ------------------------------------------------------------------ fixtures
insert into auth.users (id, email, aud, role) values
  ('00000000-0000-4000-8000-00000000a001', 'rls-student-a@example.invalid', 'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a002', 'rls-student-b@example.invalid', 'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a003', 'rls-staff-it@example.invalid',  'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a004', 'rls-staff-fin@example.invalid', 'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a005', 'rls-admin@example.invalid',     'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a006', 'rls-advisor-1@example.invalid', 'authenticated', 'authenticated'),
  ('00000000-0000-4000-8000-00000000a007', 'rls-advisor-2@example.invalid', 'authenticated', 'authenticated');

insert into public.profiles (id, role, office, alias) values
  ('00000000-0000-4000-8000-00000000a001', 'student', null,      'rls-student-a'),
  ('00000000-0000-4000-8000-00000000a002', 'student', null,      'rls-student-b'),
  ('00000000-0000-4000-8000-00000000a003', 'staff',   'it',      'rls-staff-it'),
  ('00000000-0000-4000-8000-00000000a004', 'staff',   'finance', 'rls-staff-fin'),
  ('00000000-0000-4000-8000-00000000a005', 'admin',   null,      'rls-admin'),
  ('00000000-0000-4000-8000-00000000a006', 'staff',   'academic', 'rls-advisor-1'),
  ('00000000-0000-4000-8000-00000000a007', 'staff',   'academic', 'rls-advisor-2');

insert into public.requests (id, alias, raw_text, lang, status) values
  ('00000000-0000-4000-8000-0000000b0001', 'rls-student-a', 'wifi down in M', 'en', 'decided'),
  ('00000000-0000-4000-8000-0000000b0002', 'rls-student-b', 'refund for fees', 'en', 'decided');

insert into public.predictions (id, request_id, category, priority, flags) values
  ('00000000-0000-4000-8000-0000000c0001', '00000000-0000-4000-8000-0000000b0001', 'IT Support', 'high',
   array['urgency_unsupported', 'priority_gaming_suspected', 'needs_review']),
  ('00000000-0000-4000-8000-0000000c0002', '00000000-0000-4000-8000-0000000b0002', 'Finance', 'medium', '{}'),
  ('00000000-0000-4000-8000-0000000c0003', '00000000-0000-4000-8000-0000000b0002', 'Academic Support', 'medium', '{}');

insert into public.tickets (id, request_id, office, category, priority, sla_due_at) values
  ('00000000-0000-4000-8000-0000000d0001', '00000000-0000-4000-8000-0000000b0001', 'it',      'IT Support', 'high',   now() + interval '4 hours'),
  ('00000000-0000-4000-8000-0000000d0002', '00000000-0000-4000-8000-0000000b0002', 'finance', 'Finance',    'medium', now() + interval '1 day');

insert into public.review_queue (prediction_id, reason) values
  ('00000000-0000-4000-8000-0000000c0001', 'rls fixture'),
  ('00000000-0000-4000-8000-0000000c0001', 'distress');

-- academic items (office filled by trigger from the category, 0012): one per advisor, one unassigned
insert into public.review_queue (prediction_id, reason, assignee) values
  ('00000000-0000-4000-8000-0000000c0003', 'rls advisor', '00000000-0000-4000-8000-00000000a006'),
  ('00000000-0000-4000-8000-0000000c0003', 'rls advisor', '00000000-0000-4000-8000-00000000a007'),
  ('00000000-0000-4000-8000-0000000c0003', 'rls advisor', null);

insert into public.notifications (alias, kind) values
  ('office:it', 'rls fixture'), ('office:finance', 'rls fixture'), ('rls-student-a', 'rls fixture');

insert into public.request_embeddings (request_id, embedding, lang, category, priority) values
  ('00000000-0000-4000-8000-0000000b0001', array_fill(0.1::real, array[384])::extensions.vector, 'en', 'IT Support', 'high');

-- ------------------------------------------------------------------ checks
do $$
declare
  v_a   constant uuid := '00000000-0000-4000-8000-00000000a001';
  v_it  constant uuid := '00000000-0000-4000-8000-00000000a003';
  v_adm constant uuid := '00000000-0000-4000-8000-00000000a005';
  v_adv constant uuid := '00000000-0000-4000-8000-00000000a006';
  n_own int; n_other int; n int; m int; v_flags text[]; v_err text;
begin
  -- 1. student A sees own request, not student B's
  perform set_config('request.jwt.claims', json_build_object('sub', v_a, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n_own from public.requests where alias = 'rls-student-a';
  select count(*) into n_other from public.requests where alias = 'rls-student-b';
  reset role;
  insert into _rls values (1, 'student A cannot read student B requests', n_own = 1 and n_other = 0,
                           format('own=%s other=%s', n_own, n_other));

  -- 2. IT staff see IT tickets, not Finance tickets
  perform set_config('request.jwt.claims', json_build_object('sub', v_it, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n_own from public.tickets where office = 'it';
  select count(*) into n_other from public.tickets where office = 'finance';
  reset role;
  insert into _rls values (2, 'IT staff cannot read Finance tickets', n_own = 1 and n_other = 0,
                           format('it=%s finance=%s', n_own, n_other));

  -- 3. an authenticated insert fails
  perform set_config('request.jwt.claims', json_build_object('sub', v_a, 'role', 'authenticated')::text, true);
  v_err := null;
  begin
    set local role authenticated;
    insert into public.requests (alias, raw_text, status) values ('rls-student-a', 'forged', 'received');
    reset role;
  exception when others then
    v_err := sqlstate || ' ' || sqlerrm;
  end;
  reset role;
  insert into _rls values (3, 'authenticated insert is rejected', v_err is not null, coalesce(v_err, 'insert succeeded'));

  -- 4. a student cannot select request_embeddings
  v_err := null; n := null;
  begin
    set local role authenticated;
    select count(*) into n from public.request_embeddings;
  exception when others then
    v_err := sqlstate || ' ' || sqlerrm;
  end;
  reset role;
  insert into _rls values (4, 'student cannot read request_embeddings', v_err is not null or n = 0,
                           coalesce(v_err, format('rows=%s', n)));

  -- 5. a student cannot execute match_vectors
  v_err := null;
  begin
    set local role authenticated;
    perform * from public.match_vectors('requests', array_fill(0.1::real, array[384])::extensions.vector, 5, 0.0, '{}');
  exception when others then
    v_err := sqlstate || ' ' || sqlerrm;
  end;
  reset role;
  insert into _rls values (5, 'student cannot execute match_vectors', v_err like '42501%', coalesce(v_err, 'executed'));

  -- 6. anon sees nothing
  perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);
  v_err := null; n := null;
  begin
    set local role anon;
    select count(*) into n from public.requests;
  exception when others then
    v_err := sqlstate || ' ' || sqlerrm;
  end;
  reset role;
  insert into _rls values (6, 'anon reads nothing', v_err is not null or n = 0, coalesce(v_err, format('rows=%s', n)));

  -- 7. admin sees every fixture request and ticket
  perform set_config('request.jwt.claims', json_build_object('sub', v_adm, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.requests where alias like 'rls-%';
  select count(*) into m from public.tickets where request_id in (
    '00000000-0000-4000-8000-0000000b0001', '00000000-0000-4000-8000-0000000b0002');
  reset role;
  insert into _rls values (7, 'admin reads everything', n = 2 and m = 2, format('requests=%s tickets=%s', n, m));

  -- 8. staff see review_queue, students do not
  perform set_config('request.jwt.claims', json_build_object('sub', v_it, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.review_queue where reason = 'rls fixture';
  reset role;
  perform set_config('request.jwt.claims', json_build_object('sub', v_a, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into m from public.review_queue;
  reset role;
  insert into _rls values (8, 'staff read review_queue (students do not)', n = 1 and m = 0,
                           format('staff=%s student=%s', n, m));

  -- 9. a student sees own prediction without gaming flags, and cannot read the base table
  set local role authenticated;
  select flags into v_flags from public.predictions_student_v
    where id = '00000000-0000-4000-8000-0000000c0001';
  select count(*) into n from public.predictions;
  reset role;
  insert into _rls values (9, 'student sees no gaming flags',
    v_flags is not null and v_flags = array['needs_review'] and n = 0,
    format('view_flags=%s base_rows=%s', v_flags, n));

  -- 10. IT staff read office:it notifications, not office:finance or a student's (0010)
  perform set_config('request.jwt.claims', json_build_object('sub', v_it, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n_own from public.notifications where kind = 'rls fixture' and alias = 'office:it';
  select count(*) into n_other from public.notifications where kind = 'rls fixture' and alias <> 'office:it';
  reset role;
  insert into _rls values (10, 'IT staff read only office:it notifications', n_own = 1 and n_other = 0,
                           format('office_it=%s others=%s', n_own, n_other));

  -- 11. distress review items are admin-only (0011)
  set local role authenticated;
  select count(*) into n from public.review_queue where reason = 'distress';
  reset role;
  perform set_config('request.jwt.claims', json_build_object('sub', v_adm, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into m from public.review_queue where reason = 'distress'
    and prediction_id = '00000000-0000-4000-8000-0000000c0001';
  reset role;
  insert into _rls values (11, 'staff never read distress review items (admin does)', n = 0 and m = 1,
                           format('staff=%s admin=%s', n, m));

  -- 12. an advisor reads their own items and the unassigned academic queue, not another advisor's (0012)
  perform set_config('request.jwt.claims', json_build_object('sub', v_adv, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) filter (where assignee = v_adv or assignee is null),
         count(*) filter (where assignee is not null and assignee <> v_adv)
    into n_own, n_other from public.review_queue where reason = 'rls advisor';
  reset role;
  insert into _rls values (12, 'advisor reads own + unassigned academic items only', n_own = 2 and n_other = 0,
                           format('own_or_queue=%s other_advisor=%s', n_own, n_other));

  -- 13. IT staff read no academic review items (0012)
  perform set_config('request.jwt.claims', json_build_object('sub', v_it, 'role', 'authenticated')::text, true);
  set local role authenticated;
  select count(*) into n from public.review_queue where reason = 'rls advisor';
  reset role;
  insert into _rls values (13, 'IT staff read no academic review items', n = 0, format('rows=%s', n));
end $$;

select n, name, ok, detail from _rls
union all
select 99, format('RLS: %s/%s checks passed', count(*) filter (where ok), count(*)), bool_and(ok), null from _rls
order by n;

rollback;
