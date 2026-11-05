-- P10.1: private, consented notification address. Apply after 0015.
alter table public.profiles
  add column notify_email text,
  add column notify_email_consent_at timestamptz,
  add constraint profiles_notify_email_pair check
    ((notify_email is null and notify_email_consent_at is null) or
     (notify_email is not null and notify_email_consent_at is not null));

-- profiles_read lets admins read every row. Replace table-wide SELECT with the
-- existing public columns so the new private address cannot leak through RLS.
revoke select on public.profiles from authenticated;
grant select (id, role, office, alias, advisor_id, display_name,
              student_number, faculty, university_email, demo_inbox)
  on public.profiles to authenticated;
grant select, update (notify_email, notify_email_consent_at)
  on public.profiles to service_role;

create table public.profile_email_changes (
  id bigint generated always as identity primary key,
  profile_id uuid not null references public.profiles(id) on delete cascade,
  changed_at timestamptz not null default now()
);
create index profile_email_changes_window_idx on public.profile_email_changes(profile_id, changed_at desc);
alter table public.profile_email_changes enable row level security;
revoke all on public.profile_email_changes from anon, authenticated;
grant select, insert, delete on public.profile_email_changes to service_role;

-- A row lock serializes concurrent writes for one account. Return a status
-- instead of a SQL exception so PostgREST can distinguish a rate limit.
create function public.cp_set_notification_email(p_profile_id uuid, p_email text,
                                                   p_limit int default 5, p_window_seconds int default 3600)
returns text language plpgsql security definer set search_path = public as $$
declare p public.profiles%rowtype;
begin
  if p_limit < 1 or p_window_seconds < 1 then return 'invalid'; end if;
  select * into p from public.profiles where id = p_profile_id for update;
  if not found then return 'missing'; end if;
  if p.notify_email = p_email and p.notify_email_consent_at is not null then return 'unchanged'; end if;
  if (select count(*) from public.profile_email_changes
      where profile_id = p_profile_id and changed_at > now() - make_interval(secs => p_window_seconds)) >= p_limit
  then return 'limited'; end if;
  update public.profiles set notify_email = p_email, notify_email_consent_at = now()
    where id = p_profile_id;
  insert into public.profile_email_changes(profile_id) values (p_profile_id);
  return 'saved';
end $$;
revoke execute on function public.cp_set_notification_email(uuid,text,int,int) from public, anon, authenticated;
grant execute on function public.cp_set_notification_email(uuid,text,int,int) to service_role;

create function public.cp_remove_notification_email(p_profile_id uuid)
returns void language sql security definer set search_path = public as $$
  update public.profiles set notify_email = null, notify_email_consent_at = null where id = p_profile_id;
$$;
revoke execute on function public.cp_remove_notification_email(uuid) from public, anon, authenticated;
grant execute on function public.cp_remove_notification_email(uuid) to service_role;
