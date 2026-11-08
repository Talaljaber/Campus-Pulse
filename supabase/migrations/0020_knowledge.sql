-- 0020_knowledge: the admin knowledge base the chat can quote (P10.19,
-- docs/plan/p10/P10.19_knowledge_base.md). Depends on 0005 (pgvector, match_vectors).
--   knowledge_documents  one row per uploaded document (no text: the text lives in its passages)
--   knowledge_chunks     its passages (~400 chars), embedded with the frozen e5 encoder (384-d, "query: ")
-- Only the AI service (service role) reads and writes them: no client role has any grant or policy.
-- match_vectors is replaced with the same signature and gains a `knowledge` collection; the requests,
-- memory and faq branches are copied unchanged from 0005.

create table public.knowledge_documents (
  id          uuid primary key default gen_random_uuid(),
  title       text not null check (char_length(title) between 1 and 200),
  filename    text check (filename is null or char_length(filename) between 1 and 200),
  office      text check (office in ('registrar', 'it', 'finance', 'transport', 'facilities', 'academic')),
  char_count  int not null default 0 check (char_count >= 0),
  chunk_count int not null default 0 check (chunk_count between 0 and 300),
  uploaded_by text,
  created_at  timestamptz not null default now()
);

create table public.knowledge_chunks (
  id          uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.knowledge_documents (id) on delete cascade,
  ord         int not null check (ord >= 0),
  text        text not null check (char_length(text) between 1 and 2000),
  lang        text not null default 'en' check (lang in ('en', 'ar')),
  embedding   extensions.vector(384) not null,
  created_at  timestamptz not null default now()
);

-- Same HNSW settings as the other vector tables (0005).
create index knowledge_chunks_embedding_hnsw on public.knowledge_chunks
  using hnsw (embedding extensions.vector_cosine_ops) with (m = 16, ef_construction = 64);
-- The foreign key (cascade delete, the join in match_vectors) and one passage per position.
create unique index knowledge_chunks_document_ord_idx on public.knowledge_chunks (document_id, ord);
create index knowledge_documents_created_idx on public.knowledge_documents (created_at desc, id desc);

alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks    enable row level security;
revoke all on public.knowledge_documents, public.knowledge_chunks from anon, authenticated;
grant select, insert, update, delete on public.knowledge_documents, public.knowledge_chunks to service_role;
-- No policy for any client role: RLS on and no grant = no access (the service role bypasses RLS).

-- ---------------------------------------------------------------- match_vectors (+ knowledge)
-- Filters (p_filters jsonb) as in 0005, plus   knowledge: office, document_id
-- knowledge meta: {document_id, title, office, ord}

create or replace function public.match_vectors(
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

  elsif p_collection = 'knowledge' then
    return query
      select c.id, c.text, c.lang, c.sim, c.meta, case when v_with then c.embedding end
      from (
        select k.id, k.text, k.lang,
               1 - (k.embedding <=> p_query) as sim,
               jsonb_build_object('document_id', k.document_id, 'title', d.title,
                                  'office', d.office, 'ord', k.ord) as meta,
               k.embedding
        from public.knowledge_chunks k
        join public.knowledge_documents d on d.id = k.document_id
        where (v_f ->> 'office' is null or d.office = v_f ->> 'office')
          and (v_f ->> 'document_id' is null or k.document_id = (v_f ->> 'document_id')::uuid)
        order by k.embedding <=> p_query
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

-- `create or replace` keeps the grants of 0005; restated so this file alone shows who may call it.
revoke execute on function public.match_vectors(text, extensions.vector, int, float8, jsonb)
  from public, anon, authenticated;
grant execute on function public.match_vectors(text, extensions.vector, int, float8, jsonb) to service_role;
