-- P10.3: staff-reviewed drafts and durable publication mail outbox.
-- Depends on 0017 (incidents may have unknown/campus scope).

create table public.announcement_drafts (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null unique references public.incidents(id) on delete cascade,
  office text not null check (office in ('registrar', 'it', 'finance', 'transport', 'facilities', 'academic')),
  title text not null check (char_length(title) between 1 and 120),
  body text not null check (char_length(body) between 1 and 1000),
  status text not null default 'pending' check (status in ('pending', 'published', 'dismissed')),
  version int not null default 1 check (version > 0),
  published_announcement_id uuid unique references public.announcements(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz,
  author_id uuid references public.profiles(id) on delete set null,
  check ((status = 'published') = (published_announcement_id is not null))
);
create index announcement_drafts_office_status_idx on public.announcement_drafts(office, status, created_at desc);
alter table public.announcement_drafts enable row level security;
create policy announcement_drafts_staff_read on public.announcement_drafts for select to authenticated
  using ((select private.cp_is_admin()) or ((select private.cp_role()) = 'staff' and office = (select private.cp_office())));
revoke all on public.announcement_drafts from anon, authenticated;
grant select (id, incident_id, office, title, body, status, version, published_announcement_id,
              created_at, updated_at, published_at, author_id) on public.announcement_drafts to authenticated;
grant select, insert, update, delete on public.announcement_drafts to service_role;

create table public.announcement_broadcasts (
  id uuid primary key default gen_random_uuid(),
  announcement_id uuid not null unique references public.announcements(id) on delete cascade,
  created_at timestamptz not null default now(),
  status text not null default 'pending' check (status in ('pending', 'running', 'done'))
);
create table public.announcement_broadcast_deliveries (
  id uuid primary key default gen_random_uuid(),
  broadcast_id uuid not null references public.announcement_broadcasts(id) on delete cascade,
  recipient_key text not null,
  recipient_address text not null,
  status text not null default 'pending' check (status in ('pending', 'claimed', 'sent', 'failed', 'skipped')),
  attempt_count int not null default 0 check (attempt_count >= 0),
  claimed_at timestamptz,
  last_error text,
  sent_at timestamptz,
  unique (broadcast_id, recipient_key)
);
create index announcement_broadcast_deliveries_pending_idx
  on public.announcement_broadcast_deliveries(status, claimed_at) where status in ('pending', 'claimed', 'failed');
alter table public.announcement_broadcasts enable row level security;
alter table public.announcement_broadcast_deliveries enable row level security;
revoke all on public.announcement_broadcasts, public.announcement_broadcast_deliveries from anon, authenticated;
grant select, insert, update, delete on public.announcement_broadcasts, public.announcement_broadcast_deliveries to service_role;

-- Called through the service role after the application checks four distinct reporters.
-- The unique incident key makes repeated threshold checks idempotent, including after dismissal.
create function public.cp_suggest_announcement(
  p_incident_id uuid, p_office text, p_title text, p_body text
) returns public.announcement_drafts language plpgsql security definer set search_path = public as $$
declare result public.announcement_drafts;
begin
  insert into public.announcement_drafts(incident_id, office, title, body)
    values (p_incident_id, p_office, p_title, p_body)
    on conflict (incident_id) do nothing;
  select * into result from public.announcement_drafts where incident_id = p_incident_id;
  return result;
end; $$;

-- One compare-and-swap operation for staff edits/dismissal; no races between two editors.
create function public.cp_change_announcement_draft(
  p_id uuid, p_version int, p_title text, p_body text, p_dismiss boolean
) returns public.announcement_drafts language plpgsql security definer set search_path = public as $$
declare result public.announcement_drafts;
begin
  update public.announcement_drafts
    set title = case when p_dismiss then title else p_title end,
        body = case when p_dismiss then body else p_body end,
        status = case when p_dismiss then 'dismissed' else 'pending' end,
        version = version + 1, updated_at = now()
    where id = p_id and version = p_version and status = 'pending'
    returning * into result;
  return result; -- null means stale version or already finalized
end; $$;

-- Exactly one live announcement and broadcast job per draft, even for concurrent publish calls.
create function public.cp_publish_announcement_draft(
  p_id uuid, p_version int, p_author uuid
) returns public.announcement_drafts language plpgsql security definer set search_path = public as $$
declare draft public.announcement_drafts;
declare new_id uuid;
begin
  select * into draft from public.announcement_drafts where id = p_id for update;
  if not found then return null; end if;
  if draft.status = 'published' then return draft; end if;
  if draft.status <> 'pending' or draft.version <> p_version then return null; end if;
  insert into public.announcements(office, kind, title, body, created_by)
    values (draft.office, 'outage', draft.title, draft.body, p_author)
    returning id into new_id;
  update public.announcement_drafts
    set status = 'published', version = version + 1, updated_at = now(),
        published_at = now(), published_announcement_id = new_id, author_id = p_author
    where id = p_id returning * into draft;
  insert into public.announcement_broadcasts(announcement_id) values (new_id);
  return draft;
end; $$;

revoke all on function public.cp_suggest_announcement(uuid,text,text,text),
  public.cp_change_announcement_draft(uuid,int,text,text,boolean),
  public.cp_publish_announcement_draft(uuid,int,uuid) from public, anon, authenticated;
grant execute on function public.cp_suggest_announcement(uuid,text,text,text),
  public.cp_change_announcement_draft(uuid,int,text,text,boolean),
  public.cp_publish_announcement_draft(uuid,int,uuid) to service_role;

-- Prepare delivery rows idempotently; callers enumerate only currently consented or configured demo recipients.
create function public.cp_prepare_announcement_delivery(p_announcement_id uuid, p_key text, p_address text)
returns void language plpgsql security definer set search_path = public as $$
declare job_id uuid;
begin
  select id into job_id from public.announcement_broadcasts where announcement_id = p_announcement_id;
  if job_id is null then return; end if;
  insert into public.announcement_broadcast_deliveries(broadcast_id, recipient_key, recipient_address)
    values (job_id, p_key, p_address)
    on conflict (broadcast_id, recipient_key) do nothing;
end; $$;

-- Concurrent workers claim different rows. Claimed rows are recoverable after five minutes.
create function public.cp_claim_announcement_delivery()
returns public.announcement_broadcast_deliveries language plpgsql security definer set search_path = public as $$
declare row public.announcement_broadcast_deliveries;
begin
  select * into row from public.announcement_broadcast_deliveries
    where attempt_count < 3 and (
      status in ('pending', 'failed') or (status = 'claimed' and claimed_at < now() - interval '5 minutes')
    )
    order by id for update skip locked limit 1;
  if not found then return null; end if;
  update public.announcement_broadcast_deliveries
    set status = 'claimed', claimed_at = now(), attempt_count = attempt_count + 1
    where id = row.id returning * into row;
  return row;
end; $$;

create function public.cp_finish_announcement_delivery(p_id uuid, p_status text, p_error text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_status not in ('sent', 'failed', 'skipped') then raise exception 'invalid delivery status'; end if;
  update public.announcement_broadcast_deliveries
    set status = p_status, last_error = left(p_error, 500), sent_at = case when p_status = 'sent' then now() else null end
    where id = p_id and status = 'claimed';
end; $$;

revoke all on function public.cp_prepare_announcement_delivery(uuid,text,text),
  public.cp_claim_announcement_delivery(), public.cp_finish_announcement_delivery(uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.cp_prepare_announcement_delivery(uuid,text,text),
  public.cp_claim_announcement_delivery(), public.cp_finish_announcement_delivery(uuid,text,text)
  to service_role;
