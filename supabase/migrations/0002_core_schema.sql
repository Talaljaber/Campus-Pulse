-- 0002_core_schema: every remaining SPEC §8 table except faq/memory_examples (0005),
-- plus the P4.1 additions (notifications, ticket_links.last_error, llm_calls cache columns,
-- outbox.channel/error, requests.simulated). Label spellings match domain/labels.py and
-- status values match domain/values.py exactly. RLS is enabled here; policies are in 0003.

alter table public.requests
  add column simulated       boolean not null default false,
  add column conversation_id uuid;

create index requests_alias_created_idx on public.requests (alias, created_at desc);
create index requests_created_idx on public.requests (created_at desc);

create table public.clarifications (
  id          uuid primary key default gen_random_uuid(),
  request_id  uuid not null references public.requests (id) on delete cascade,
  question_id text not null,
  options     jsonb not null default '[]',
  answer      text,
  asked_at    timestamptz not null default now(),
  answered_at timestamptz,
  created_at  timestamptz not null default now()
);

create index clarifications_request_idx on public.clarifications (request_id, asked_at);

-- office is denormalised from the routing table so staff RLS needs no join (§3.14).
create table public.incidents (
  id           uuid primary key default gen_random_uuid(),
  building_id  text not null references public.buildings (id),
  category     text not null check (category in (
                 'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
                 'Academic Support')),
  office       text,
  title        text not null default '',
  priority     text not null check (priority in ('low', 'medium', 'high')),
  report_count int not null default 0,
  status       text not null default 'open' check (status in ('open', 'resolved')),
  opened_at    timestamptz not null default now(),
  resolved_at  timestamptz,
  created_at   timestamptz not null default now()
);

create index incidents_building_status_idx on public.incidents (building_id, status);

create table public.tickets (
  id           uuid primary key default gen_random_uuid(),
  request_id   uuid not null references public.requests (id) on delete cascade,
  incident_id  uuid references public.incidents (id) on delete set null,
  office       text not null,
  category     text not null check (category in (
                 'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
                 'Academic Support')),
  priority     text not null check (priority in ('low', 'medium', 'high')),
  status       text not null default 'open' check (status in (
                 'open', 'in_progress', 'resolved', 'closed', 'escalated', 'merged')),
  provisional  boolean not null default false,
  title        text not null default '',
  body         text not null default '',
  sla_due_at   timestamptz not null,
  escalated_at timestamptz,
  resolved_at  timestamptz,
  created_at   timestamptz not null default now()
);

create index tickets_office_status_sla_idx on public.tickets (office, status, sla_due_at);
create index tickets_request_idx on public.tickets (request_id);
create index tickets_incident_idx on public.tickets (incident_id) where incident_id is not null;

create table public.ticket_links (
  ticket_id      uuid not null references public.tickets (id) on delete cascade,
  sink           text not null,
  external_id    text not null,
  external_url   text,
  last_synced_at timestamptz,
  last_error     text,
  created_at     timestamptz not null default now(),
  primary key (ticket_id, sink),
  unique (sink, external_id)
);

-- Seed data is fictional only: names are aliases, demo_email must be allow-listed.
create table public.advisors (
  id             uuid primary key default gen_random_uuid(),
  fictional_name text not null,
  department     text not null,
  room           text,
  calendar_id    text,
  demo_email     text,
  office_hours   jsonb,
  created_at     timestamptz not null default now()
);

-- SPEC calls these start/end; renamed to match domain Slot and avoid the reserved word.
create table public.advisor_slots (
  id         uuid primary key default gen_random_uuid(),
  advisor_id uuid not null references public.advisors (id) on delete cascade,
  starts_at  timestamptz not null,
  ends_at    timestamptz not null,
  booked_by  text,
  booked_at  timestamptz,
  created_at timestamptz not null default now(),
  unique (advisor_id, starts_at),
  check (ends_at > starts_at)
);

create index advisor_slots_free_idx on public.advisor_slots (advisor_id, starts_at) where booked_by is null;

create table public.cases (
  id           uuid primary key default gen_random_uuid(),
  request_id   uuid references public.requests (id) on delete cascade,
  ticket_id    uuid references public.tickets (id) on delete set null,
  advisor_id   uuid references public.advisors (id) on delete set null,
  slot_id      uuid references public.advisor_slots (id) on delete set null,
  slot_start   timestamptz,
  outcome_code text,
  booking      jsonb,
  closed_at    timestamptz,
  created_at   timestamptz not null default now()
);

-- kind is the purpose (SPEC §8); channel is the transport (domain OutboxMessage.kind).
create table public.outbox (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null default 'email' check (kind in (
                'email', 'ticket', 'booking', 'alert', 'broadcast', 'in_app', 'whatsapp')),
  channel     text not null default 'email' check (channel in ('email', 'in_app', 'whatsapp')),
  alias       text,
  request_id  uuid references public.requests (id) on delete set null,
  to_address  text not null,
  subject     text not null default '',
  body        text not null default '',
  provider_id text,
  status      text not null check (status in ('queued', 'sent', 'failed', 'rejected', 'simulated')),
  priority    text check (priority in ('low', 'medium', 'high')),
  flags       text[] not null default '{}',
  error       text,
  created_at  timestamptz not null default now()
);

create index outbox_created_idx on public.outbox (created_at desc);
create index outbox_alias_idx on public.outbox (alias, created_at desc);

create table public.notifications (
  id         uuid primary key default gen_random_uuid(),
  alias      text not null,
  kind       text not null,
  payload    jsonb not null default '{}',
  read_at    timestamptz,
  created_at timestamptz not null default now()
);

create index notifications_alias_idx on public.notifications (alias, created_at desc);

create table public.review_queue (
  id                 uuid primary key default gen_random_uuid(),
  prediction_id      uuid not null references public.predictions (id) on delete cascade,
  reason             text not null,
  status             text not null default 'open' check (status in ('open', 'confirmed', 'corrected')),
  reviewer_id        uuid references auth.users (id) on delete set null,
  corrected_category text check (corrected_category in (
                       'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
                       'Academic Support')),
  corrected_priority text check (corrected_priority in ('low', 'medium', 'high')),
  note               text,
  created_at         timestamptz not null default now(),
  resolved_at        timestamptz
);

create index review_queue_status_idx on public.review_queue (status, created_at);

create table public.student_signals (
  alias                     text primary key,
  n_requests                int not null default 0,
  n_claimed_urgent          int not null default 0,
  n_claimed_urgent_not_high int not null default 0,
  n_high                    int not null default 0,
  n_injection               int not null default 0,
  gaming_flag               boolean not null default false,
  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

-- cache_key/response back SupabaseCache (LD-25).
create table public.llm_calls (
  id          uuid primary key default gen_random_uuid(),
  request_id  uuid references public.requests (id) on delete set null,
  tier        text check (tier in ('tier0', 'tier1', 'tier2', 'human')),
  model       text not null,
  prompt_hash text not null,
  cache_key   text unique,
  response    jsonb,
  tokens_in   int not null default 0,
  tokens_out  int not null default 0,
  cost_usd    numeric(10, 6) not null default 0,
  latency_ms  int,
  cached      boolean not null default false,
  created_at  timestamptz not null default now()
);

create index llm_calls_created_idx on public.llm_calls (created_at desc);

create table public.redteam_runs (
  id         uuid primary key default gen_random_uuid(),
  config     jsonb not null default '{}',
  scorecard  jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- Audit log (append-only by convention; only the service role writes).
create table public.events (
  id         bigint generated always as identity primary key,
  actor      text not null,
  action     text not null,
  entity     text not null,
  payload    jsonb not null default '{}',
  at         timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index events_at_idx on public.events (at desc);

alter table public.clarifications  enable row level security;
alter table public.incidents       enable row level security;
alter table public.tickets         enable row level security;
alter table public.ticket_links    enable row level security;
alter table public.advisors        enable row level security;
alter table public.advisor_slots   enable row level security;
alter table public.cases           enable row level security;
alter table public.outbox          enable row level security;
alter table public.notifications   enable row level security;
alter table public.review_queue    enable row level security;
alter table public.student_signals enable row level security;
alter table public.llm_calls       enable row level security;
alter table public.redteam_runs    enable row level security;
alter table public.events          enable row level security;
