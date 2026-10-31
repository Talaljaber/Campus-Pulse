-- 0007_repository: what SupabaseRepository needs to round-trip the domain entities losslessly
-- (P4.3), plus an atomic counter RPC and the incident office fill-in for staff RLS.

-- NormalizedRequest fields that had no column (0001 stores core/text_norm/lang/... already).
alter table public.requests
  add column model_text      text,
  add column truncated       boolean not null default false,
  add column location_source text check (location_source in ('picked', 'extracted'));

-- The full CoreResult (ProbVectors with label order, evidence, guard verdict, neighbours,
-- floors, ood score). The flat columns (p_cat, set_cat, flags, ...) stay for the UI and SQL.
alter table public.predictions
  add column core jsonb;

-- Read-modify-write over PostgREST would lose concurrent bumps, so the counters are updated
-- in one statement. gaming_flag is left as stored: GamingDetector decides it (P3.6).
create function public.bump_student_signals(
  p_alias text, p_claimed_urgent boolean, p_was_high boolean, p_injection boolean
) returns public.student_signals
  language sql volatile security definer set search_path = public
as $$
  insert into public.student_signals as s
    (alias, n_requests, n_claimed_urgent, n_claimed_urgent_not_high, n_high, n_injection, updated_at)
  values (p_alias, 1, p_claimed_urgent::int, (p_claimed_urgent and not p_was_high)::int,
          p_was_high::int, p_injection::int, now())
  on conflict (alias) do update set
    n_requests                = s.n_requests + 1,
    n_claimed_urgent          = s.n_claimed_urgent + excluded.n_claimed_urgent,
    n_claimed_urgent_not_high = s.n_claimed_urgent_not_high + excluded.n_claimed_urgent_not_high,
    n_high                    = s.n_high + excluded.n_high,
    n_injection               = s.n_injection + excluded.n_injection,
    updated_at                = now()
  returning s.*
$$;

revoke execute on function public.bump_student_signals(text, boolean, boolean, boolean)
  from public, anon, authenticated;
grant execute on function public.bump_student_signals(text, boolean, boolean, boolean) to service_role;

-- Incident has no office in the domain; staff RLS (0003) needs one. Take it from the first
-- ticket attached to the incident.
create function private.cp_fill_incident_office() returns trigger
  language plpgsql security definer set search_path = public
as $$
begin
  if new.incident_id is not null then
    update public.incidents set office = new.office where id = new.incident_id and office is null;
  end if;
  return new;
end;
$$;

revoke execute on function private.cp_fill_incident_office() from public, anon, authenticated;

create trigger tickets_fill_incident_office
  after insert or update of incident_id on public.tickets
  for each row execute function private.cp_fill_incident_office();
