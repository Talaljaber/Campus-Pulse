-- 0009_ticket_tags_outbox_deferred: schema for decision D-011 (P4.3).
--
-- tickets.tags: free-form labels the action engine attaches to a ticket, e.g. `safety`,
-- `transport-alert`, `exam-in-progress`, `unconfirmed`, `deferred:<kind>`. Staff filter and badge
-- on them. `authenticated` holds a table-level SELECT on tickets (0003) and no view selects from
-- tickets, so the column is readable under the existing tickets_read policy with no extra grant.
--
-- outbox.status 'deferred': a side effect (Linear sync, email, booking) that the engine parked
-- instead of sending, e.g. outside office hours or while a dependency is down. The inline check
-- from 0002 is re-created with the same values plus 'deferred'.

alter table public.tickets add column tags text[] not null default '{}';

alter table public.outbox drop constraint outbox_status_check;
alter table public.outbox add constraint outbox_status_check
  check (status in ('queued', 'sent', 'failed', 'rejected', 'simulated', 'deferred'));
