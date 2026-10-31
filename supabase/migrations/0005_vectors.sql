-- 0005_vectors: pgvector collections (ARCHITECTURE §3.18, P4.2). All embeddings come from the
-- frozen encoder (384-d, e5 "query: " prefix); vector type lives in schema "extensions".
--   collection  table               written by                read by
--   requests    request_embeddings  TriageUseCase (online)    incidents, recurring problems
--   memory      memory_examples     FeedbackUseCase           live-learning kNN
--   faq         faq                 scripts/seed_faq.py       FAQ answer-first retrieval
-- Clients never see an embedding: request_embeddings has no client policy, memory_examples
-- and faq expose only non-embedding columns (column grants + *_v views), and the RPCs are
-- service-role only.

create table public.faq (
  id         uuid primary key default gen_random_uuid(),
  lang       text not null check (lang in ('en', 'ar')),
  question   text not null,
  answer     text not null,
  source_url text,
  is_demo    boolean not null default true,
  embedding  extensions.vector(384),
  created_at timestamptz not null default now()
);

create table public.memory_examples (
  id         uuid primary key default gen_random_uuid(),
  text_norm  text not null,
  lang       text not null check (lang in ('en', 'ar', 'arabizi')),
  embedding  extensions.vector(384) not null,
  category   text not null check (category in (
               'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
               'Academic Support')),
  priority   text not null check (priority in ('low', 'medium', 'high')),
  author_id  uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  active     boolean not null default true
);

create table public.request_embeddings (
  request_id  uuid primary key references public.requests (id) on delete cascade,
  embedding   extensions.vector(384) not null,
  lang        text check (lang in ('en', 'ar', 'arabizi')),
  category    text check (category in (
                'Registration', 'IT Support', 'Finance', 'Transportation', 'Facilities',
                'Academic Support')),
  priority    text check (priority in ('low', 'medium', 'high')),
  building_id text references public.buildings (id),
  room        text,
  created_at  timestamptz not null default now()
);

-- HNSW: no training data needed (IVFFlat on a tiny table recalls badly), build cost is
-- irrelevant below 10 k rows.
create index faq_embedding_hnsw on public.faq
  using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64);
create index memory_examples_embedding_hnsw on public.memory_examples
  using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64);
create index request_embeddings_embedding_hnsw on public.request_embeddings
  using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64);

create index memory_examples_active_created_idx on public.memory_examples (active, created_at);
create index request_embeddings_filter_idx on public.request_embeddings (building_id, category, created_at);

-- ---------------------------------------------------------------- RPCs
-- One dispatcher for all three collections. Filters (p_filters jsonb):
--   requests: building_id, category, since     memory: active (default true), lang, category, since
--   faq: lang                                  all: with_embedding (LD-14; else embedding is null)
-- The inner query takes an ANN candidate pool (4k, min 40) in index order; the outer query
-- applies min_sim and re-sorts by (sim desc, id) so ties break deterministically even with
-- iterative_scan = relaxed_order (pgvector 0.8.2 on this project).

create function public.match_vectors(
  p_collection text,
  p_query      extensions.vector(384),
  p_k          int,
  p_min_sim    float8 default 0,
  p_filters    jsonb default '{}'
) returns table (id uuid, text text, lang text, sim float8, meta jsonb, embedding extensions.vector(384))
  language plpgsql stable security definer
  set search_path = public, extensions
  set hnsw.ef_search = 40
  set hnsw.iterative_scan = relaxed_order
as $$
#variable_conflict use_column
declare
  v_k     int := least(greatest(coalesce(p_k, 0), 0), 1000);
  v_pool  int := greatest(least(greatest(coalesce(p_k, 0), 0), 1000) * 4, 40);
  v_f     jsonb := coalesce(p_filters, '{}');
  v_with  boolean := coalesce((v_f ->> 'with_embedding')::boolean, false);
  v_since timestamptz := (v_f ->> 'since')::timestamptz;
  v_min   float8 := coalesce(p_min_sim, 0);
begin
  if v_k = 0 then
    return;
  end if;

  if p_collection = 'requests' then
    return query
      select c.id, c.text, c.lang, c.sim, c.meta, case when v_with then c.embedding end
      from (
        select e.request_id as id,
               coalesce(r.text_norm, r.core, r.raw_text) as text,
               coalesce(e.lang, r.lang, 'en') as lang,
               1 - (e.embedding <=> p_query) as sim,
               jsonb_build_object('building_id', e.building_id, 'room', e.room,
                                  'category', e.category, 'priority', e.priority,
                                  'created_at', e.created_at) as meta,
               e.embedding
        from public.request_embeddings e
        join public.requests r on r.id = e.request_id
        where (v_f ->> 'building_id' is null or e.building_id = v_f ->> 'building_id')
          and (v_f ->> 'category' is null or e.category = v_f ->> 'category')
          and (v_since is null or e.created_at >= v_since)
        order by e.embedding <=> p_query
        limit v_pool
      ) c
      where c.sim >= v_min
      order by c.sim desc, c.id
      limit v_k;

  elsif p_collection = 'memory' then
    return query
      select c.id, c.text, c.lang, c.sim, c.meta, case when v_with then c.embedding end
      from (
        select m.id, m.text_norm as text, m.lang,
               1 - (m.embedding <=> p_query) as sim,
               jsonb_build_object('category', m.category, 'priority', m.priority,
                                  'author_id', m.author_id, 'created_at', m.created_at,
                                  'active', m.active) as meta,
               m.embedding
        from public.memory_examples m
        where m.active = coalesce((v_f ->> 'active')::boolean, true)
          and (v_f ->> 'lang' is null or m.lang = v_f ->> 'lang')
          and (v_f ->> 'category' is null or m.category = v_f ->> 'category')
          and (v_since is null or m.created_at >= v_since)
        order by m.embedding <=> p_query
        limit v_pool
      ) c
      where c.sim >= v_min
      order by c.sim desc, c.id
      limit v_k;

  elsif p_collection = 'faq' then
    return query
      select c.id, c.text, c.lang, c.sim, c.meta, case when v_with then c.embedding end
      from (
        select f.id, f.question as text, f.lang,
               1 - (f.embedding <=> p_query) as sim,
               jsonb_build_object('answer', f.answer, 'source_url', f.source_url,
                                  'is_demo', f.is_demo) as meta,
               f.embedding
        from public.faq f
        where f.embedding is not null
          and (v_f ->> 'lang' is null or f.lang = v_f ->> 'lang')
        order by f.embedding <=> p_query
        limit v_pool
      ) c
      where c.sim >= v_min
      order by c.sim desc, c.id
      limit v_k;

  else
    raise exception 'match_vectors: unknown collection %', p_collection using errcode = '22023';
  end if;
end;
$$;

-- Startup check for PgVectorStore: the declared dimension of the vector columns.
create function public.vector_dim() returns int
  language sql stable security definer set search_path = public, extensions
  as $$ select atttypmod from pg_attribute where attrelid = 'public.faq'::regclass and attname = 'embedding' $$;

revoke execute on function public.match_vectors(text, extensions.vector, int, float8, jsonb), public.vector_dim()
  from public, anon, authenticated;
grant execute on function public.match_vectors(text, extensions.vector, int, float8, jsonb), public.vector_dim()
  to service_role;

-- ---------------------------------------------------------------- RLS + column privileges

alter table public.faq                enable row level security;
alter table public.memory_examples    enable row level security;
alter table public.request_embeddings enable row level security;

revoke all on public.faq, public.memory_examples, public.request_embeddings from anon, authenticated;
grant select (id, lang, question, answer, source_url, is_demo, created_at) on public.faq to authenticated;
grant select (id, text_norm, lang, category, priority, author_id, created_at, active)
  on public.memory_examples to authenticated;
-- request_embeddings: no grant and no policy for any client role (service role only).

create policy faq_read on public.faq for select to authenticated
  using (true);

create policy memory_examples_read on public.memory_examples for select to authenticated
  using ((select public.cp_is_staff()));

create view public.faq_v with (security_invoker = true) as
  select id, lang, question, answer, source_url, is_demo from public.faq;

create view public.memory_examples_v with (security_invoker = true) as
  select id, text_norm, lang, category, priority, author_id, created_at, active from public.memory_examples;

revoke all on public.faq_v, public.memory_examples_v from anon;
grant select on public.faq_v, public.memory_examples_v to authenticated;
