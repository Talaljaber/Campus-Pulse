-- 0013_student_journey: P9 student journey (accounts, statuses, clock, thread, announcements, hints).

-- profiles: fictional directory fields (never real data)
alter table public.profiles
  add column display_name     text,
  add column student_number   text unique,
  add column faculty          text,
  add column university_email text unique,   -- fictional, shown on Profile, never mailed
  add column demo_inbox       text;          -- optional delivery override (must still pass DEMO_EMAIL_ALLOWLIST)

-- tickets: status rename + clock
alter table public.tickets drop constraint tickets_status_check;
update public.tickets set status = case status
  when 'open' then 'new' when 'resolved' then 'solved' when 'escalated' then 'in_progress' else status end;
alter table public.tickets add constraint tickets_status_check
  check (status in ('new', 'in_progress', 'solved', 'closed', 'merged'));
alter table public.tickets alter column status set default 'new';
alter table public.tickets
  add column clock_started_at timestamptz,
  add column reminder_sent_at timestamptz,
  add column awaiting_student boolean not null default false,
  add column requester_alias  text;
update public.tickets set clock_started_at = created_at where clock_started_at is null;
alter table public.tickets alter column clock_started_at set not null,
                           alter column clock_started_at set default now();
update public.tickets t set requester_alias = r.alias from public.requests r where r.id = t.request_id;
create index tickets_requester_alias_idx on public.tickets (requester_alias);
create index tickets_open_due_idx on public.tickets (sla_due_at) where status in ('new', 'in_progress');

create function private.cp_fill_ticket_requester() returns trigger
  language plpgsql security definer set search_path = public as $$
begin
  if new.requester_alias is null then
    select r.alias into new.requester_alias from public.requests r where r.id = new.request_id;
  end if;
  return new;
end; $$;
revoke execute on function private.cp_fill_ticket_requester() from public, anon, authenticated;
create trigger tickets_fill_requester before insert on public.tickets
  for each row execute function private.cp_fill_ticket_requester();

-- helpers
create function private.cp_owns_ticket(p_ticket_id uuid) returns boolean
  language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.tickets t
                   where t.id = p_ticket_id and private.cp_owns_request(t.request_id)) $$;
-- staff of the ticket's office who are NOT its requester (a staff member never works their own ticket)
create function private.cp_ticket_office_staff(p_ticket_id uuid) returns boolean
  language sql stable security definer set search_path = public as $$
    select private.cp_role() = 'staff' and exists (
      select 1 from public.tickets t
      where t.id = p_ticket_id and t.office = private.cp_office()
        and not private.cp_owns_request(t.request_id)) $$;
revoke execute on function private.cp_owns_ticket(uuid), private.cp_ticket_office_staff(uuid) from public, anon;
grant execute on function private.cp_owns_ticket(uuid), private.cp_ticket_office_staff(uuid)
  to authenticated, service_role;

-- thread
create table public.ticket_activity (
  id            uuid primary key default gen_random_uuid(),
  ticket_id     uuid not null references public.tickets (id) on delete cascade,
  kind          text not null check (kind in ('created', 'comment', 'note', 'status', 'forward',
                                              'priority', 'student_action', 'reminder')),
  visibility    text not null default 'public' check (visibility in ('public', 'internal')),
  actor_role    text not null check (actor_role in ('student', 'staff', 'admin', 'system')),
  actor_alias   text,
  actor_office  text,
  body          text not null default '' check (char_length(body) <= 4000),
  from_status   text, to_status   text,
  from_office   text, to_office   text,
  from_priority text, to_priority text,
  created_at    timestamptz not null default now(),
  check (kind not in ('note', 'reminder') or visibility = 'internal')
);
create index ticket_activity_ticket_idx on public.ticket_activity (ticket_id, created_at);
alter table public.ticket_activity enable row level security;
create policy ticket_activity_read on public.ticket_activity for select to authenticated using (
  (select private.cp_is_admin())
  or private.cp_ticket_office_staff(ticket_id)
  or (visibility = 'public' and private.cp_owns_ticket(ticket_id)));

-- announcements
create table public.announcements (
  id          uuid primary key default gen_random_uuid(),
  office      text check (office in ('registrar', 'it', 'finance', 'transport', 'facilities', 'academic')),
  kind        text not null default 'info' check (kind in ('info', 'outage', 'maintenance')),
  title       text not null check (char_length(title) between 1 and 120),
  body        text not null check (char_length(body) between 1 and 1000),
  starts_at   timestamptz not null default now(),
  ends_at     timestamptz,
  archived_at timestamptz,
  created_by  uuid references public.profiles (id) on delete set null,
  created_at  timestamptz not null default now(),
  check (ends_at is null or ends_at > starts_at)
);
create index announcements_live_idx on public.announcements (starts_at desc) where archived_at is null;
alter table public.announcements enable row level security;
create policy announcements_read on public.announcements for select to authenticated
  using (archived_at is null or (select private.cp_is_staff()));

-- hints (staff corrections for the chat agent's retrieval; never read by predict.py / frozen model)
create table public.ticket_hints (
  id                 uuid primary key default gen_random_uuid(),
  ticket_id          uuid references public.tickets (id) on delete set null,
  kind               text not null check (kind in ('forward', 'priority')),
  request_text       text not null,
  lang               text,
  embedding          extensions.vector(384),
  model_category     text, model_priority text,
  corrected_category text not null check (corrected_category in ('Registration', 'IT Support', 'Finance',
                       'Transportation', 'Facilities', 'Academic Support')),
  corrected_priority text not null check (corrected_priority in ('low', 'medium', 'high')),
  note               text,
  author_alias       text,
  author_role        text,
  created_at         timestamptz not null default now()
);
create index ticket_hints_created_idx on public.ticket_hints (created_at desc);
alter table public.ticket_hints enable row level security;
create policy ticket_hints_read on public.ticket_hints for select to authenticated
  using ((select private.cp_is_staff()));

create function public.match_ticket_hints(p_query extensions.vector(384), p_k int, p_min_sim float8)
  returns table (id uuid, request_text text, corrected_category text, corrected_priority text,
                 model_category text, model_priority text, kind text, sim float8, created_at timestamptz)
  language sql stable security definer set search_path = public, extensions as $$
    select h.id, h.request_text, h.corrected_category, h.corrected_priority, h.model_category,
           h.model_priority, h.kind, 1 - (h.embedding <=> p_query) as sim, h.created_at
    from public.ticket_hints h
    where h.embedding is not null and 1 - (h.embedding <=> p_query) >= coalesce(p_min_sim, 0)
    order by h.embedding <=> p_query, h.created_at desc
    limit least(greatest(coalesce(p_k, 0), 0), 20) $$;
revoke execute on function public.match_ticket_hints(extensions.vector, int, float8) from public, anon, authenticated;
grant execute on function public.match_ticket_hints(extensions.vector, int, float8) to service_role;

-- privileges (0003 default privileges already deny client writes; be explicit anyway)
revoke all on public.ticket_activity, public.announcements, public.ticket_hints from anon;
revoke insert, update, delete, truncate, references, trigger
  on public.ticket_activity, public.announcements, public.ticket_hints from authenticated;
grant select on public.ticket_activity, public.announcements to authenticated;
revoke select on public.ticket_hints from authenticated;
grant select (id, ticket_id, kind, request_text, lang, model_category, model_priority, corrected_category,
              corrected_priority, note, author_alias, author_role, created_at) on public.ticket_hints to authenticated;
grant select, insert, update, delete on public.ticket_activity, public.announcements, public.ticket_hints
  to service_role;

alter publication supabase_realtime add table public.ticket_activity, public.announcements;
