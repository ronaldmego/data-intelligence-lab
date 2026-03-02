# TODO — #17 Complete API Coverage (Read Tools)

## Plan
Add 8 read tools to `server.py` + wire them in `app.py`. All follow the same `api_get` + format pattern.

## Tasks
- [x] Add `list_stored_procedures` — /storedProcedures
- [x] Add `list_policies` — /policies
- [x] Add `list_roles` — /roles
- [x] Add `list_services` — /services/{type}Services (flexible)
- [x] Add `list_pipelines` — /pipelines
- [x] Add `list_dashboards` — /dashboards
- [x] Add `list_topics` — /topics
- [x] Add `list_data_products` — /dataProducts
- [x] Wire all 8 in `app.py` (import + TOOLS list)
- [x] Test against live OM instance — all 8 work
- [x] Update changelog, ROADMAP
- [ ] PR with `Closes #17`

## Results
- 27 total tools (17 read + 10 write)
- All tested against live OM 1.11.7: stored procedures (131), policies (14), roles (14), services (1), pipelines (0), dashboards (0), topics (0), data products (0)
- `list_services` supports 7 service types via `service_type` parameter
- Version bumped to 1.0.0
