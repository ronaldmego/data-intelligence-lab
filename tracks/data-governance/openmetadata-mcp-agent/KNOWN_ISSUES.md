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
