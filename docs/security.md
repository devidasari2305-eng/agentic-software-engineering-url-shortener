# Security, compliance and change control

## Autonomy boundaries

| Boundary | Enforcement |
|---|---|
| Agents never deploy | No deployment capability exists; requirements asking for it are blocked by POL-001 |
| Agents write only to the workflow workspace | `Workspace` rejects paths outside the root and the checkpoint store (POL-006) |
| Human approval before code is generated and before release | Gates `G1` / `G2` block execution |
| Approvals are human | Approver names like `agent`, `system`, `ai`, `bot` are refused |
| High-impact changes need a written acknowledgement | `requires_comment` when risk is high or POL-010/011/012 trigger |

## Policy rules (all evaluated and recorded)

Requirement rules: POL-001 no autonomous production changes, POL-002 governance cannot be
bypassed, POL-003 no destructive data operations, POL-004 no secrets (all **block**); POL-010
schema/data change, POL-011 high risk, POL-012 sensitive data (all **require approval**).

Generated-code rules: POL-020 no `eval`/`exec`, POL-021 no process execution, POL-022 no unsafe
deserialization, POL-023 no hard-coded secrets, POL-024 no outbound network imports (all **block**).

## Product controls

Typed input validation (http/https only), unique codes, bounded code allocation, atomic click
increments, redirect-loop rejection (a target that points back to this service), expiry and disable
handling (410), parameterised SQL through SQLAlchemy.

## Not implemented in the prototype (production roadmap)

Authentication and RBAC for approvers (identity is asserted, not verified), rate limiting,
SSRF/private-network and reputation checks on target URLs, SAST/DAST and SBOM in CI, encrypted and
externally anchored audit storage, signed artifacts, and protected deployment environments.
`ALLOW_FAULT_INJECTION` must be `false` in any real environment.
