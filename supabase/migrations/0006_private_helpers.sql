-- 0006_private_helpers: move the RLS helpers (0003) out of the PostgREST-exposed public schema,
-- so they are no longer callable as /rest/v1/rpc/cp_* (Supabase lint 0029). Policies and
-- predictions_student_v store function OIDs, so they keep working after the move. Helpers that
-- call other helpers are re-created in place (same OID) to reference private.*.
-- authenticated keeps EXECUTE: policy expressions run as the querying role.

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated, service_role;

alter function public.cp_role()                   set schema private;
alter function public.cp_office()                 set schema private;
alter function public.cp_alias()                  set schema private;
alter function public.cp_is_staff()               set schema private;
alter function public.cp_is_admin()               set schema private;
alter function public.cp_owns_request(uuid)       set schema private;
alter function public.cp_office_has_request(uuid) set schema private;
alter function public.cp_can_see_ticket(uuid)     set schema private;
alter function public.cp_student_predictions()    set schema private;

create or replace function private.cp_is_staff() returns boolean
  language sql stable security definer set search_path = public
  as $$ select coalesce(private.cp_role() in ('staff', 'admin'), false) $$;

create or replace function private.cp_is_admin() returns boolean
  language sql stable security definer set search_path = public
  as $$ select coalesce(private.cp_role() = 'admin', false) $$;

create or replace function private.cp_owns_request(p_request_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select exists (
      select 1 from public.requests r
      where r.id = p_request_id and r.alias is not null and r.alias = private.cp_alias())
  $$;

create or replace function private.cp_office_has_request(p_request_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select private.cp_role() = 'staff' and exists (
      select 1 from public.tickets t
      where t.request_id = p_request_id and t.office = private.cp_office())
  $$;

create or replace function private.cp_can_see_ticket(p_ticket_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select exists (
      select 1 from public.tickets t
      where t.id = p_ticket_id
        and ((private.cp_role() = 'staff' and t.office = private.cp_office())
             or private.cp_owns_request(t.request_id)))
  $$;

create or replace function private.cp_student_predictions()
  returns table (
    id uuid, request_id uuid, category text, priority text, p_cat jsonb, p_pri jsonb,
    set_cat text[], set_pri text[], tier text, flags text[], explanation jsonb,
    artifact_version text, created_at timestamptz)
  language sql stable security definer set search_path = public
  as $$
    select p.id, p.request_id, p.category, p.priority, p.p_cat, p.p_pri, p.set_cat, p.set_pri,
           p.tier,
           array(select f from unnest(p.flags) as f
                 where f not in ('urgency_unsupported', 'priority_gaming_suspected')),
           p.explanation, p.artifact_version, p.created_at
    from public.predictions p
    join public.requests r on r.id = p.request_id
    where r.alias is not null and r.alias = private.cp_alias()
  $$;
