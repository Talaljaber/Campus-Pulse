-- 0008_fk_indexes: cover every foreign key the Supabase performance advisor flagged
-- (lint 0001_unindexed_foreign_keys). Without them, deleting a request (cascades/set null into
-- cases, outbox, llm_calls), a prediction (review_queue) or an auth user (memory_examples,
-- review_queue) scans the child table, and the joins the UI and repository make on these
-- columns cannot use an index.

create index cases_advisor_id_idx            on public.cases (advisor_id);
create index cases_request_id_idx            on public.cases (request_id);
create index cases_slot_id_idx               on public.cases (slot_id);
create index cases_ticket_id_idx             on public.cases (ticket_id);
create index llm_calls_request_id_idx        on public.llm_calls (request_id);
create index memory_examples_author_id_idx   on public.memory_examples (author_id);
create index outbox_request_id_idx           on public.outbox (request_id);
create index requests_building_id_idx        on public.requests (building_id);
create index review_queue_prediction_id_idx  on public.review_queue (prediction_id);
create index review_queue_reviewer_id_idx    on public.review_queue (reviewer_id);
