-- P10.17: the admin overview. One read-only function returns the operational numbers a university
-- administrator needs (volume, backlog, SLA, per-office performance, AI handling, delivery health),
-- computed in the database so the page stays fast as the tables grow. Admin only: anyone else gets
-- an error. Simulated traffic (requests.simulated) is left out of every count.

create or replace function public.cp_admin_overview(p_days int default 30)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  since timestamptz;
  result jsonb;
begin
  if not coalesce((select private.cp_is_admin()), false) then
    raise exception 'admin only' using errcode = '42501';
  end if;
  since := now() - make_interval(days => greatest(1, least(coalesce(p_days, 30), 365)));

  with
  req as (
    select r.* from public.requests r
    where r.created_at >= since and not coalesce(r.simulated, false)
  ),
  tix as (
    select t.* from public.tickets t
    join public.requests r on r.id = t.request_id
    where not coalesce(r.simulated, false) and t.status <> 'merged'
  ),
  done as (
    select t.*, extract(epoch from (t.resolved_at - t.created_at)) / 3600.0 as hours
    from tix t
    where t.status in ('solved', 'closed') and t.resolved_at is not null and t.resolved_at >= since
  ),
  offices as (
    select o.office from (values ('registrar'), ('it'), ('finance'), ('transport'), ('facilities'), ('academic'))
      as o(office)
  ),
  per_office as (
    select
      o.office,
      (select count(*) from tix t where t.office = o.office and t.status in ('new', 'in_progress')) as open,
      (select count(*) from tix t where t.office = o.office and t.status in ('new', 'in_progress')
         and t.sla_due_at < now() and not coalesce(t.awaiting_student, false)) as overdue,
      (select count(*) from tix t where t.office = o.office and t.status in ('new', 'in_progress')
         and t.priority = 'high') as high_open,
      (select count(*) from tix t where t.office = o.office and t.created_at >= since) as received,
      (select count(*) from done d where d.office = o.office) as resolved,
      (select round(percentile_cont(0.5) within group (order by d.hours)::numeric, 1)
         from done d where d.office = o.office) as median_hours,
      (select round(100.0 * avg(case when d.resolved_at <= d.sla_due_at then 1 else 0 end), 0)
         from done d where d.office = o.office) as sla_met_pct
    from offices o
  ),
  days as (
    select generate_series(date_trunc('day', since), date_trunc('day', now()), interval '1 day') as day
  ),
  daily as (
    select to_char(d.day, 'YYYY-MM-DD') as day,
           (select count(*) from req r where date_trunc('day', r.created_at) = d.day) as requests,
           (select count(*) from req r
              join public.tickets t on t.request_id = r.id
             where date_trunc('day', r.created_at) = d.day and t.priority = 'high') as high
    from days d
  ),
  preds as (
    select distinct on (p.request_id) p.request_id, p.tier
    from public.predictions p join req r on r.id = p.request_id
    order by p.request_id, p.created_at desc
  ),
  reviews as (
    select q.* from public.review_queue q where q.created_at >= since
  ),
  mail as (
    select o.* from public.outbox o where o.created_at >= since
  )
  select jsonb_build_object(
    'days', extract(day from now() - since)::int,
    'generated_at', now(),
    'requests', jsonb_build_object(
      'total', (select count(*) from req),
      'by_lang', jsonb_build_object(
        'en', (select count(*) from req where lang = 'en'),
        'ar', (select count(*) from req where lang = 'ar'),
        'arabizi', (select count(*) from req where lang = 'arabizi')),
      'voice', (select count(*) from req where input_mode = 'voice'),
      'distress', (select count(*) from req where status = 'distress'),
      'out_of_scope', (select count(*) from req where status = 'out_of_scope'),
      'students', (select count(distinct alias) from req where alias is not null)),
    'tickets', jsonb_build_object(
      'open', (select count(*) from tix where status in ('new', 'in_progress')),
      'overdue', (select count(*) from tix where status in ('new', 'in_progress') and sla_due_at < now()
                     and not coalesce(awaiting_student, false)),
      'high_open', (select count(*) from tix where status in ('new', 'in_progress') and priority = 'high'),
      'received', (select count(*) from tix where created_at >= since),
      'resolved', (select count(*) from done),
      'median_hours', (select round(percentile_cont(0.5) within group (order by hours)::numeric, 1) from done),
      'sla_met_pct', (select round(100.0 * avg(case when resolved_at <= sla_due_at then 1 else 0 end), 0)
                        from done)),
    'offices', (select coalesce(jsonb_agg(to_jsonb(po) order by po.office), '[]'::jsonb) from per_office po),
    'daily', (select coalesce(jsonb_agg(to_jsonb(d) order by d.day), '[]'::jsonb) from daily d),
    'ai', jsonb_build_object(
      'classified', (select count(*) from preds),
      'automatic', (select count(*) from preds where tier in ('tier0', 'tier1', 'tier2')),
      'to_human', (select count(*) from preds where tier = 'human'),
      'asked_question', (select count(distinct c.request_id) from public.clarifications c
                           join req r on r.id = c.request_id),
      'reviews', (select count(*) from reviews),
      'reviews_open', (select count(*) from public.review_queue where status = 'open'),
      'corrected', (select count(*) from reviews where status = 'corrected'),
      'confirmed', (select count(*) from reviews where status = 'confirmed')),
    'incidents', jsonb_build_object(
      'open', (select count(*) from public.incidents where status = 'open'),
      'opened', (select count(*) from public.incidents where opened_at >= since)),
    'delivery', jsonb_build_object(
      'sent', (select count(*) from mail where status = 'sent'),
      'failed', (select count(*) from mail where status = 'failed'),
      'rejected', (select count(*) from mail where status = 'rejected'),
      'queued', (select count(*) from mail where status in ('queued', 'deferred')),
      'sync_errors', (select count(*) from public.ticket_links where last_error is not null),
      'synced', (select count(*) from public.ticket_links where last_error is null)),
    'people', jsonb_build_object(
      'students', (select count(*) from public.profiles where role = 'student'),
      'staff', (select count(*) from public.profiles where role = 'staff'),
      'admins', (select count(*) from public.profiles where role = 'admin'))
  ) into result;
  return result;
end;
$$;

revoke all on function public.cp_admin_overview(int) from public, anon;
grant execute on function public.cp_admin_overview(int) to authenticated;
