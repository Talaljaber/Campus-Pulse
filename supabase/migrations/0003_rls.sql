-- 0003_rls: read-only RLS surface for client roles (ARCHITECTURE §3.14).
-- Client roles (anon, authenticated) get SELECT policies only; every write comes from
-- FastAPI with the service role, which bypasses RLS. anon gets nothing at all.
--
-- Cross-table checks (e.g. "staff may read a request if their office holds its ticket")
-- go through security-definer helpers: a policy on requests that queried tickets, while
-- tickets' policy queried requests, would raise "infinite recursion detected in policy".

-- ---------------------------------------------------------------- helpers

create function public.cp_role() returns text
  language sql stable security definer set search_path = public
  as $$ select role from public.profiles where id = auth.uid() $$;

create function public.cp_office() returns text
  language sql stable security definer set search_path = public
  as $$ select office from public.profiles where id = auth.uid() $$;

create function public.cp_alias() returns text
  language sql stable security definer set search_path = public
  as $$ select alias from public.profiles where id = auth.uid() $$;

create function public.cp_is_staff() returns boolean
  language sql stable security definer set search_path = public
  as $$ select coalesce(public.cp_role() in ('staff', 'admin'), false) $$;

create function public.cp_is_admin() returns boolean
  language sql stable security definer set search_path = public
  as $$ select coalesce(public.cp_role() = 'admin', false) $$;

-- The caller owns the request (its alias matches the caller's profile alias).
create function public.cp_owns_request(p_request_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select exists (
      select 1 from public.requests r
      where r.id = p_request_id and r.alias is not null and r.alias = public.cp_alias())
  $$;

-- The caller is staff and a ticket for the request is routed to the caller's office.
create function public.cp_office_has_request(p_request_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select public.cp_role() = 'staff' and exists (
      select 1 from public.tickets t
      where t.request_id = p_request_id and t.office = public.cp_office())
  $$;

create function public.cp_can_see_ticket(p_ticket_id uuid) returns boolean
  language sql stable security definer set search_path = public
  as $$
    select exists (
      select 1 from public.tickets t
      where t.id = p_ticket_id
        and ((public.cp_role() = 'staff' and t.office = public.cp_office())
             or public.cp_owns_request(t.request_id)))
  $$;

revoke execute on function
  public.cp_role(), public.cp_office(), public.cp_alias(), public.cp_is_staff(),
  public.cp_is_admin(), public.cp_owns_request(uuid), public.cp_office_has_request(uuid),
  public.cp_can_see_ticket(uuid)
  from public, anon;
grant execute on function
  public.cp_role(), public.cp_office(), public.cp_alias(), public.cp_is_staff(),
  public.cp_is_admin(), public.cp_owns_request(uuid), public.cp_office_has_request(uuid),
  public.cp_can_see_ticket(uuid)
  to authenticated, service_role;

-- ---------------------------------------------------------------- privileges
-- Belt and braces on top of RLS: clients can never write, anon can never read.

revoke all on all tables in schema public from anon;
revoke insert, update, delete, truncate, references, trigger on all tables in schema public from authenticated;
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke insert, update, delete, truncate, references, trigger on tables from authenticated;

-- ---------------------------------------------------------------- policies
-- (select fn()) lets Postgres evaluate the helper once per statement (initplan).

create policy profiles_read on public.profiles for select to authenticated
  using (id = (select auth.uid()) or (select public.cp_is_admin()));

create policy buildings_read on public.buildings for select to authenticated
  using (true);

create policy requests_read on public.requests for select to authenticated
  using (
    (alias is not null and alias = (select public.cp_alias()))
    or public.cp_office_has_request(id)
    or (select public.cp_is_admin()));

-- Students read predictions only through predictions_student_v (flags stripped).
create policy predictions_read on public.predictions for select to authenticated
  using (public.cp_office_has_request(request_id) or (select public.cp_is_admin()));

create policy clarifications_read on public.clarifications for select to authenticated
  using (
    public.cp_owns_request(request_id)
    or public.cp_office_has_request(request_id)
    or (select public.cp_is_admin()));

create policy tickets_read on public.tickets for select to authenticated
  using (
    ((select public.cp_role()) = 'staff' and office = (select public.cp_office()))
    or public.cp_owns_request(request_id)
    or (select public.cp_is_admin()));

create policy ticket_links_read on public.ticket_links for select to authenticated
  using (public.cp_can_see_ticket(ticket_id) or (select public.cp_is_admin()));

create policy incidents_read on public.incidents for select to authenticated
  using (
    ((select public.cp_role()) = 'staff' and office = (select public.cp_office()))
    or (select public.cp_is_admin()));

create policy advisors_read on public.advisors for select to authenticated
  using (true);

create policy advisor_slots_read on public.advisor_slots for select to authenticated
  using ((select public.cp_is_staff()));

create policy cases_read on public.cases for select to authenticated
  using ((select public.cp_is_staff()));

create policy outbox_read on public.outbox for select to authenticated
  using ((alias is not null and alias = (select public.cp_alias())) or (select public.cp_is_staff()));

create policy notifications_read on public.notifications for select to authenticated
  using (alias = (select public.cp_alias()) or (select public.cp_is_admin()));

create policy review_queue_read on public.review_queue for select to authenticated
  using ((select public.cp_is_staff()));

create policy student_signals_read on public.student_signals for select to authenticated
  using ((select public.cp_is_admin()));

create policy llm_calls_read on public.llm_calls for select to authenticated
  using ((select public.cp_is_staff()));

create policy redteam_runs_read on public.redteam_runs for select to authenticated
  using ((select public.cp_is_staff()));

create policy events_read on public.events for select to authenticated
  using ((select public.cp_is_staff()));

-- ---------------------------------------------------------------- student predictions view
-- A security_invoker view over the student's own rows cannot hide flags: the student would
-- need a row policy on predictions and could select flags directly. So the row filter and
-- the flag stripping live in a security-definer function, and the view (security_invoker,
-- as §3.14 asks) wraps it. Students have no policy on predictions itself.

create function public.cp_student_predictions()
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
    where r.alias is not null and r.alias = public.cp_alias()
  $$;

revoke execute on function public.cp_student_predictions() from public, anon;
grant execute on function public.cp_student_predictions() to authenticated, service_role;

create view public.predictions_student_v with (security_invoker = true) as
  select * from public.cp_student_predictions();

revoke all on public.predictions_student_v from anon;
grant select on public.predictions_student_v to authenticated;
