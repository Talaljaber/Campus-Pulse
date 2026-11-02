-- P9.10: files on tickets. A private Storage bucket (no client policies: the AI service, with the
-- service role, is the only writer and the only one who signs links) plus a `ticket_files` table that
-- records each file and carries the access rules (same shape as `ticket_activity`).
--
-- Storage objects are NOT removed when a ticket (and so its `ticket_files` rows) is deleted: the FK
-- cascade only removes the rows. Demo-sized data; a cleanup job is out of scope.
-- Not applied by the build: the lead applies it (and checks the bucket exists afterwards).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'ticket-files', 'ticket-files', false, 5242880,
  array[
    'image/png', 'image/jpeg', 'image/webp', 'application/pdf', 'text/plain',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ]
)
on conflict (id) do nothing;
-- Deliberately no policies on storage.objects for anon or authenticated: with RLS on and no policy,
-- clients can neither list, read nor write objects. Links are signed by the service role, 60 s each.

create table public.ticket_files (
  id             uuid primary key default gen_random_uuid(),
  ticket_id      uuid not null references public.tickets (id) on delete cascade,
  activity_id    uuid references public.ticket_activity (id) on delete set null,
  uploader_alias text,
  uploader_role  text not null check (uploader_role in ('student', 'staff', 'admin')),
  visibility     text not null default 'public' check (visibility in ('public', 'internal')),
  storage_path   text not null unique,  -- tickets/<ticket_id>/<uuid>.<ext>; never the original filename
  mime           text not null,
  size_bytes     int  not null check (size_bytes between 1 and 5242880),
  ext            text not null,
  created_at     timestamptz not null default now()
);
create index ticket_files_ticket_idx on public.ticket_files (ticket_id, created_at);
create index ticket_files_activity_idx on public.ticket_files (activity_id);

alter table public.ticket_files enable row level security;
create policy ticket_files_read on public.ticket_files for select to authenticated using (
  (select private.cp_is_admin())
  or private.cp_ticket_office_staff(ticket_id)
  or (visibility = 'public' and private.cp_owns_ticket(ticket_id)));

-- privileges: clients read a few columns (never the storage path), only the service role writes
revoke all on public.ticket_files from anon;
revoke insert, update, delete, truncate, references, trigger on public.ticket_files from authenticated;
revoke select on public.ticket_files from authenticated;
grant select (id, ticket_id, activity_id, uploader_role, visibility, mime, size_bytes, ext, created_at)
  on public.ticket_files to authenticated;
grant select, insert, update, delete on public.ticket_files to service_role;

-- advisor-suggested FK indexes (lead, 2026-11-02)
create index if not exists announcements_created_by_idx on public.announcements (created_by);
create index if not exists ticket_hints_ticket_id_idx on public.ticket_hints (ticket_id);
