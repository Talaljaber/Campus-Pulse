-- 0012_advisor_routing: hybrid advisor routing (UD-13).
--
-- * profiles.advisor_id: a student's own advisor (advisors row). Students read it on their own
--   profile row (profiles_read, 0003); only the service role writes profiles.
-- * advisors.profile_id: the staff login of an advisor (unique), so an advisors row and the
--   profile that review items are assigned to can be joined.
-- * review_queue.assignee: the advisor's profile id; null = the office queue.
-- * review_queue.office: the D-005 office the item belongs to. Backend may set it; otherwise a
--   trigger fills it from the prediction's category (the 1:1 category -> office table in
--   config/actions.yaml). A prediction without a category leaves it null: admin only.
--
-- review_queue_read is narrowed to least privilege (it replaces the cross-office widening noted
-- in 0011): staff read the non-distress items of their own office that are unassigned or
-- assigned to them. An advisor (staff, office academic) therefore sees the academic office
-- queue plus their own items, never another advisor's. Distress items stay admin-only, and
-- admins read everything.

alter table public.profiles
  add column advisor_id uuid references public.advisors (id) on delete set null;
alter table public.advisors
  add column profile_id uuid unique references public.profiles (id) on delete set null;
alter table public.review_queue
  add column assignee uuid references public.profiles (id) on delete set null,
  add column office   text;

create index profiles_advisor_id_idx         on public.profiles (advisor_id);
create index review_queue_assignee_idx       on public.review_queue (assignee);
create index review_queue_office_status_idx  on public.review_queue (office, status, created_at);

create function private.cp_category_office(p_category text) returns text
  language sql immutable set search_path = public
as $$
  select case p_category
    when 'Registration'     then 'registrar'
    when 'IT Support'       then 'it'
    when 'Finance'          then 'finance'
    when 'Transportation'   then 'transport'
    when 'Facilities'       then 'facilities'
    when 'Academic Support' then 'academic'
  end
$$;

create function private.cp_fill_review_office() returns trigger
  language plpgsql security definer set search_path = public
as $$
begin
  if new.office is null then
    select private.cp_category_office(p.category) into new.office
      from public.predictions p where p.id = new.prediction_id;
  end if;
  return new;
end;
$$;

revoke execute on function private.cp_category_office(text) from public, anon, authenticated;
revoke execute on function private.cp_fill_review_office() from public, anon, authenticated;

create trigger review_queue_fill_office
  before insert on public.review_queue
  for each row execute function private.cp_fill_review_office();

update public.review_queue r
   set office = private.cp_category_office(p.category)
  from public.predictions p
 where p.id = r.prediction_id and r.office is null;

alter policy review_queue_read on public.review_queue
  using (
    (select private.cp_is_admin())
    or ((select private.cp_role()) = 'staff'
        and reason <> 'distress'
        and office = (select private.cp_office())
        and (assignee is null or assignee = (select auth.uid())))
  );
