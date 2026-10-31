-- 0010_office_notifications: staff read their office's notifications (Backend batch 5), and
-- review_queue + ticket_links stream over Realtime (UI batch 4).
--
-- Escalation notes for an office are written to notifications with alias `office:<office>`
-- (e.g. `office:it`). Staff now read the rows addressed to their own profiles.office; students
-- still read only their own alias and admins everything. notifications_read (0003) is altered in
-- place instead of adding a second permissive policy, which the performance advisor flags.
-- Students cannot take an `office:` alias: profiles are written by the service role only.
-- notifications is already in the supabase_realtime publication (0004).
--
-- Realtime applies each table's SELECT policy to postgres_changes, so subscribers receive exactly
-- the rows they can already read: review_queue -> staff and admin (review_queue_read);
-- ticket_links -> whoever can see the ticket, and admin (ticket_links_read).

alter policy notifications_read on public.notifications
  using (
    alias = (select private.cp_alias())
    or ((select private.cp_role()) = 'staff' and alias = 'office:' || (select private.cp_office()))
    or (select private.cp_is_admin())
  );

alter publication supabase_realtime add table public.review_queue, public.ticket_links;
