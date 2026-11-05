-- P10.3: optional-location shared issues, confirmed contribution accounting,
-- durable confirmation and staff announcement drafts. Apply after 0016.
alter table public.incidents alter column building_id drop not null;
alter table public.incidents add column scope text not null default 'building'
  check (scope in ('building', 'campus', 'unknown'));
alter table public.incidents add constraint incidents_scope_building check
  ((scope = 'building' and building_id is not null) or
   (scope <> 'building' and building_id is null));
alter table public.incidents add column announcement_id uuid unique references public.announcements(id) on delete set null;
create index incidents_scope_status_idx on public.incidents(scope, status);

alter table public.requests add column merge_disposition text
  check (merge_disposition in ('automatic', 'joined', 'separate'));

create table public.incident_contributions (
  incident_id uuid not null references public.incidents(id) on delete cascade,
  request_id uuid not null unique references public.requests(id) on delete cascade,
  reporter_alias text,
  created_at timestamptz not null default now(),
  primary key (incident_id, request_id)
);
create index incident_contributions_distinct_idx on public.incident_contributions(incident_id, reporter_alias);
alter table public.incident_contributions enable row level security;
revoke all on public.incident_contributions from anon, authenticated;
grant select, insert, update, delete on public.incident_contributions to service_role;

create table public.chat_confirmation_claims (
  token_digest text primary key,
  actor_alias text not null,
  request_id uuid unique,
  result jsonb,
  status text not null check (status in ('in_progress', 'completed')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
alter table public.chat_confirmation_claims enable row level security;
revoke all on public.chat_confirmation_claims from anon, authenticated;
grant select, insert, update, delete on public.chat_confirmation_claims to service_role;

create function public.cp_claim_chat_confirmation(p_token_digest text, p_actor_alias text,
                                                   p_request_id uuid, p_expires_at timestamptz)
returns jsonb language plpgsql security definer set search_path = public as $$
declare inserted text; existing public.chat_confirmation_claims%rowtype;
begin
  insert into public.chat_confirmation_claims(token_digest, actor_alias, request_id, status, expires_at)
  values (p_token_digest, p_actor_alias, p_request_id, 'in_progress', p_expires_at)
  on conflict (token_digest) do nothing returning token_digest into inserted;
  if inserted is not null then return jsonb_build_object('status', 'claimed', 'request_id', p_request_id); end if;
  select * into existing from public.chat_confirmation_claims
    where token_digest = p_token_digest for update;
  if existing.actor_alias <> p_actor_alias then return jsonb_build_object('status', 'invalid'); end if;
  return jsonb_build_object('status', existing.status, 'request_id', existing.request_id,
                            'result', existing.result);
end $$;
revoke execute on function public.cp_claim_chat_confirmation(text,text,uuid,timestamptz)
  from public, anon, authenticated;
grant execute on function public.cp_claim_chat_confirmation(text,text,uuid,timestamptz) to service_role;

create function public.cp_complete_chat_confirmation(p_token_digest text, p_result jsonb)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  update public.chat_confirmation_claims set status = 'completed', result = p_result
    where token_digest = p_token_digest and status = 'in_progress';
  return found;
end $$;
revoke execute on function public.cp_complete_chat_confirmation(text,jsonb) from public, anon, authenticated;
grant execute on function public.cp_complete_chat_confirmation(text,jsonb) to service_role;
