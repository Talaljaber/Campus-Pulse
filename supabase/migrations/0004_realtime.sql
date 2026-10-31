-- 0004_realtime: Realtime postgres_changes for the live UI. RLS applies to every event,
-- so each client only receives rows its SELECT policy allows (0003). requests is added
-- for the Pulse dots (LD-25); students subscribe to notifications only.

alter publication supabase_realtime
  add table public.predictions, public.tickets, public.incidents, public.outbox,
            public.notifications, public.requests;
