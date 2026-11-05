# P10 package E — read-only discovery (2026-11-03)

## Existing incident path

`TriageUseCase._pulse_step` stores every request embedding with nullable `building_id`, but returns before incident detection when `NormalizedRequest.location` is absent. It also limits incident actions to ticket actions. `WindowedCentroidDetector.detect` repeats the missing-location early return; it searches `request_embeddings` with a building equality filter and a 30-minute window, then uses centroid cosine similarity and three reports to form an incident. It can attach to an open incident regardless of age and fold close open incidents of one building.

`incidents.building_id` is NOT NULL in migration 0002. `tickets.incident_id` links the parent incident ticket and each member ticket. `Repository.incident_members` derives members from that link, then fetches their requests. The request embedding table has nullable building_id. `match_vectors` only applies the building equality filter when a non-null filter is supplied; an absent filter searches all buildings. Thus an unknown-location search must explicitly exclude located rows, or it can join them accidentally.

RLS: `incidents_read` in migration 0003 controls client visibility; ticket and request policies separately govern member details. Service-role stores bypass RLS. The migration must preserve those policies and not expose private report text through a new student query.

## Integration impacts

The domain `Incident.building` is currently a required `str`. Both Supabase and in-memory repositories filter on the building and serialize it as `building_id`. The Pulse map assumes a building. Package F owns the triage early return and UI flow. Package E will make the detector and stores scope-aware while preserving the existing located-report behavior.

The current membership link is usable for active incidents, but it does not distinguish a duplicate submission from another person. A new contribution table or equivalent uniqueness must be added for distinct-reporter counts and explicit separate requests. The current `report_count` counts requests, not distinct reporters.

## Implemented package E contracts

- `0017_shared_issues.sql`: nullable incident building with building/campus/unknown scope, unique linked announcement, request merge disposition, unique request contribution ledger, persistent chat confirmation claims and two service-only atomic claim/complete RPCs. Package G owns 0018 draft/broadcast schema.
- `application/services/shared_issue.py`: category plus fault-cue eligibility, with personal-cue veto. The LLM cue may supplement the fault signal but cannot override a personal cue.
- `WindowedCentroidDetector(shared_issues_enabled=False)` keeps old behavior by default. With the setting on, unknown-location reports cluster only with other unknown-location reports, and ineligible current/historical requests do not enter a cluster. `match_open(req,pred,embedding)->Incident|None` reads a currently open incident without mutation. `Incident.building` and `IncidentOut.building` are nullable; repositories use SQL `IS NULL` for unknown-location incidents.
- Package F must remove the triage early return when location is absent, wire the enable switch, implement the claim RPC client and enforce explicit separate-request bypass. Package G must count distinct reporter aliases from `incident_contributions` when drafting.

## Focused checks and remaining limits

Strict mypy passed on 219 Python modules. Ruff passed on the changed modules. `pytest -m 'not supabase'` for incident detector and profile email: 28 passed, 16 deselected; the new unknown-location test passed. A run without the marker entered a live Supabase test and its teardown failed because an existing request still references the test building; no migration was applied and no SQL cleanup was attempted. The SQL RPCs and scoped vector filtering need a live database check after 0017 is applied.

Current `report_count` still counts request rows. The distinct-reporter contribution ledger is ready, but package F/G must wire it before enabling shared issues. `match_open` handles open incidents; matching an unlinked announcement belongs to F/G. The configured 0.92 similarity threshold is a baseline until synthetic positive/negative probes set it.
