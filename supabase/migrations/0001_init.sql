-- 0001_init: extensions + the four base tables (P0.10, SPEC §8).
-- RLS is enabled on every table with no policies (deny-all for client roles);
-- policies arrive in 0003 (ARCHITECTURE §3.14). The service role bypasses RLS.

create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create table public.profiles (
  id     uuid primary key references auth.users (id) on delete cascade,
  role   text not null default 'student' check (role in ('student', 'staff', 'admin')),
  office text,
  alias  text unique
);

-- Fictional campus layout; map_x/map_y are SVG coordinates for the Pulse map.
create table public.buildings (
  id      text primary key,
  code    text unique not null,
  name_en text not null,
  name_ar text not null,
  map_x   real,
  map_y   real
);

create table public.requests (
  id             uuid primary key default gen_random_uuid(),
  alias          text,
  raw_text       text not null,
  core           text,
  text_norm      text,
  lang           text check (lang in ('en', 'ar', 'arabizi')),
  is_arabizi     boolean,
  input_mode     text check (input_mode in ('text', 'voice')),
  building_id    text references public.buildings (id),
  room           text,
  stated_urgency boolean,
  status         text not null check (status in (
                   'received', 'needs_clarification', 'clarified', 'decided', 'human_review',
                   'out_of_scope', 'distress', 'actioned', 'resolved', 'merged')),
  created_at     timestamptz not null default now()
);

create table public.predictions (
  id               uuid primary key default gen_random_uuid(),
  request_id       uuid not null references public.requests (id) on delete cascade,
  category         text check (category in (
                     'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
                     'Academic Support')),
  priority         text check (priority in ('low', 'medium', 'high')),
  p_cat            jsonb,
  p_pri            jsonb,
  set_cat          text[],
  set_pri          text[],
  per_model        jsonb,
  tier             text check (tier in ('tier0', 'tier1', 'tier2', 'human')),
  models_used      text[],
  cost_usd         numeric(10, 6),
  latency_ms       int,
  flags            text[] not null default '{}',
  explanation      jsonb,
  artifact_version text,
  created_at       timestamptz not null default now()
);

create index predictions_request_id_idx on public.predictions (request_id, created_at desc);

alter table public.profiles    enable row level security;
alter table public.buildings   enable row level security;
alter table public.requests    enable row level security;
alter table public.predictions enable row level security;
