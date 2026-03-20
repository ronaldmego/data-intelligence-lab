# Known Issues

Limitations, workarounds, and deferred fixes. Not worth fixing immediately, but must be tracked.

---

## OM-001 — Domain-to-table PATCH fails (OM 1.11.7)

**Symptom:** `assign_domain` tool (or any PATCH to assign a domain to a table) returns HTTP 500 from the OpenMetadata API.

**Root cause:** Bug in OpenMetadata 1.11.7. The PATCH endpoint for domain assignment on table entities is broken server-side.

**Workaround:** Assign domains to tables via the OpenMetadata UI manually.

**Status:** Deferred. Will resolve on OpenMetadata upgrade. The `create_domain` tool works correctly — only the table assignment step is affected.

---

## OM-002 — Classification deletion requires specific query params

**Symptom:** DELETE request to `/api/v1/classifications/{id}` returns error without specific parameters.

**Root cause:** OpenMetadata requires `?recursive=true&hardDelete=true` for classifications that have tags or are assigned to entities.

**Workaround:** Always append `?recursive=true&hardDelete=true` when deleting classifications.

**Status:** Handled in code — documented here for visibility.

---

## OM-003 — Gemini response format varies by model version

**Symptom:** Chat displays raw JSON (`[{'type': 'text', 'text': '...'}]`) instead of rendered text.

**Root cause:** Gemini 2.5 Pro sometimes returns content as a list of blocks instead of a plain string, depending on the response type.

**Workaround:** `extract_text()` function in `app.py` handles both formats. Fixed in v0.3.1.

**Status:** Fixed. Documented in case it regresses on model updates.

---

## OM-004 — Owners field is plural array, not singular object

**Symptom:** PATCH to assign owner fails silently or returns unexpected result.

**Root cause:** OpenMetadata API uses `owners` (array) not `owner` (object). Common mistake when reading older API docs.

**Workaround:** Always use `owners: [{"id": "...", "type": "user"}]` in PATCH payloads.

**Status:** Handled in code. Documented to avoid regression.

---

## OM-005 — testCaseResult returns 500 when test has never run (OM 1.11.7)

**Symptom:** `GET /dataQuality/testCases/{fqn}/testCaseResult` returns HTTP 500 for tests that exist but have never been executed.

**Root cause:** OM internally throws a 404 when looking up results for an unexecuted test and fails to handle it gracefully, surfacing as 500.

**Workaround:** Handle 500 explicitly with a user-friendly message: "test has no executions yet". Fixed in `get_test_case_results`.

**Status:** Handled in code.

---

## OM-006 — list_test_cases table filter returns empty without includeAllTests=true

**Symptom:** Filtering test cases by table `entityLink` returns empty list even when tests exist.

**Root cause:** OM 1.11.7 requires `includeAllTests=true` to return column-level tests when filtering by table entityLink. Without it only table-level tests are returned (and most tests are column-level).

**Workaround:** Always add `params["includeAllTests"] = "true"` when `entityLink` filter is used.

**Status:** Handled in code.

---

## OM-007 — ingestionPipelines FQN lookup requires /name/ prefix

**Symptom:** `GET /services/ingestionPipelines/{fqn}` returns 500.

**Root cause:** OM 1.11.7 does not support direct FQN in the path for ingestion pipelines. Must use the `/name/` variant.

**Workaround:** Use `/services/ingestionPipelines/name/{fqn}` for all FQN-based lookups.

**Status:** Handled in code.

---

## OM-008 — Pipeline must be deployed to Airflow before triggering

**Symptom:** `POST /trigger/{id}` returns 200 but DAG run stays in `queued` state forever and never executes.

**Root cause:** The DAG config file doesn't exist in Airflow's DAG store until OM deploys it. Triggering without deploying first creates a phantom run.

**Workaround:** Always call `POST /deploy/{id}` before `POST /trigger/{id}` on a new or re-created pipeline.

**Status:** Operational knowledge — not a code fix. Documented to avoid debugging the same issue.
