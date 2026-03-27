# DUTIES.md - Segregation of Duties Policy

## Purpose

This document defines the segregation of duties (SoD) policy for the OpenMetadata Agent.
**Critical for FINRA, Federal Reserve, SEC, and enterprise compliance.**

## Roles & Permissions Matrix

| Role | Can Do | Cannot Do | Rationale |
|------|--------|-----------|-----------|
| **catalog_viewer** | Search, list, get details, view lineage | Any write operation | Read-only discovery role |
| **metadata_editor** | Update descriptions, create glossary terms, assign tags | Delete operations, ownership changes | Content management without structural changes |
| **owner_assigner** | Assign/reassign ownership, approve ownership transfers | Content edits, metadata changes | Stewardship separation |
| **auditor** | View audit logs, read lineage, export compliance reports | Any modifications | Independent verification |
| **admin** | All operations | None | Break-glass emergency access (logged) |

## Conflict Matrix

These roles **cannot** be held by the same agent/user simultaneously:

```yaml
conflicts:
  - [metadata_editor, auditor]      # Cannot audit own edits
  - [owner_assigner, catalog_viewer] # Cannot assign to self without review
  - [admin, auditor]                # Admin actions need separate audit
```

## Enforcement Rules

### 1. Write Operations Require Confirmation

Any tool in the `write` category must:
1. Show a preview of the change
2. Request explicit user confirmation
3. Log the operation with before/after state

### 2. Critical Operations Require Approval

These operations need secondary approval (simulated via confirmation prompt):
- `assign_owner` — Ownership changes affect stewardship
- `create_glossary` — Glossaries are organization-wide
- `link_glossary_term` — Affects data classification

### 3. Audit Logging

Every operation logs:
- Timestamp
- User/agent identity
- Tool invoked
- Arguments (sanitized)
- Result status
- Before/after state (for writes)

## Workflow: Safe Metadata Update

```
User: "Update the description for table 'customers'"

1. Agent (as catalog_viewer): Verify table exists, show current description
2. Agent (as metadata_editor): Propose new description, show diff
3. User: Confirm
4. Agent: Execute update, log to audit
5. Agent (as auditor): Confirm update in audit log
```

## Workflow: Ownership Assignment

```
User: "Assign ownership of 'orders' table to John"

1. Agent (as catalog_viewer): Verify table and user exist
2. Agent (as owner_assigner): Check current ownership, propose change
3. Agent: Request confirmation ("This will transfer stewardship from Alice to John")
4. User: Confirm
5. Agent: Execute transfer, notify previous owner (if configured)
6. Agent (as auditor): Log ownership change with justification
```

## Emergency Procedures

**Break-glass access:** If admin override is needed:
1. Log the emergency access request
2. Require explicit confirmation with warning
3. Execute with full audit trail
4. Alert compliance team (if configured)

## Compliance Standards Mapping

| Standard | Requirement | Implementation |
|----------|-------------|----------------|
| FINRA | Supervisory controls | Role-based access, audit logs |
| Federal Reserve | SR 11-7 | Model risk management via governance |
| SEC | Recordkeeping | Immutable audit trail |
| SOX | Segregation of duties | Conflict matrix enforcement |

## Exceptions

Exceptions to SoD policy must be:
1. Documented with business justification
2. Approved by compliance officer
3. Time-bound (expiration date)
4. Fully audited

---

*This policy is enforced by the agent runtime. Any violation attempts are logged and blocked.*
