-- 0011_distress_reviews_admin_only: distress review items are for admins only (UI batch 4).
--
-- A distress request has no ticket and no routed office: TriageUseCase saves a human-tier
-- prediction, a `distress` review item and request status `distress`, and takes no action. Staff
-- RLS (requests_read, predictions_read) therefore hides its text from staff, who saw an empty
-- item. Rather than widen request access to a guessed office, staff stop receiving distress items
-- at all; admins, who already read every request, handle them. This is the least-privilege option.
--
-- Other review items stay visible to all staff across offices (known widening, kept for the
-- cross-office human-review queue; the rows carry ids and a reason, never request text).

alter policy review_queue_read on public.review_queue
  using (
    (select private.cp_is_admin())
    or ((select private.cp_role()) = 'staff' and reason <> 'distress')
  );
