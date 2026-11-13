# IEEE / ISO/IEC/IEEE 29148 SRS coverage in scenario packages

Author knowledge so the package can populate a domain graph close to an SRS
outline (29148 §9.6 / classic IEEE 830). Do **not** invent transcript quotes;
use `confirmed` only with cues.

Canonical gap list also lives in `docs/YAML_GRAPH_MODEL.md`.

## Prescribe by default (create + depth-update)

For SRS-shaped holes an LLM can **reasonably prescribe** from the brief +
transcript + already-extracted facts, **do it during package build** — do not
wait for an instructor gap batch first.

| Do by default | Hold for ask-first gap |
| --- | --- |
| Cluster FRs into named `FEAT-*` + wire `satisfies_ids` | Numeric SLAs, caps, deadlines not in cues |
| State `GOAL-*` outcomes clearly implied by cues/brief | Contradictory authority / who-wins policy |
| Remap `ASM-*` → `category: assumption`; split `DEP-*` | Elicitation boundaries that must stay unknown for students |
| Name obvious `IF-*` / `DATA-*` / `UC-*` from described flows | Sensitive privacy rules without cue support |
| Add light quality / verification hints when cues mention trust, timing, or testability | Anything you cannot ground in brief + cues + prior facts |

**Status for prescriptions**

- Prefer `status: clarified`, `origin: instructor`.
- Put `source_refs` when cues support the inference; otherwise note “no direct cue; structural prescription” in `rationale`.
- Always set `rationale` (or decision rationale later) to start with `Prescribed during authoring;` so verify/change is obvious.
- Do **not** mark prescriptions `confirmed` / `origin: transcript`.
- Do **not** use `status: assumed` until the instructor verifies (assumed needs decision provenance).

**Promote-before-invent still applies** — remap and split existing facts before minting net-new IDs.

## Verify / change path (authoring)

Prescriptions are live in YAML immediately, but authoring must expose a review path:

1. After writing prescribed facts, open (or refresh) `gaps.yaml` items with theme `srs_prescription` — one gap per prescription **cluster** (e.g. “Features + satisfies links”, not one gap per FR).
2. Each verify item lists the prescribed fact IDs, the statement summary, grounding (cues / brief / structural), and actions: `verify_accept` / `modify` / `reject` / `defer`.
3. Show the instructor a short **Prescription review** (≤ 5 clusters per batch). They may:
   - **verify_accept** — keep as `clarified`, or upgrade pure world-assumptions to `assumed` with a decision record
   - **modify** — rewrite statement / links / category; persist decision
   - **reject** — remove the fact (and fix dangling `satisfies_ids` / `known_fact_ids`)
   - **defer** — keep the prescription in YAML; leave gap open
4. Instructor shortcuts (still write decision records):
   - “verify all prescriptions” / “accept all SRS prescriptions” → `verify_accept` on open `srs_prescription` gaps
   - “apply recommended defaults for this batch” → same for the current batch

Package generation and reindex **do not block** on verify. Approval/freeze still requires the instructor to have reviewed critical prescriptions or explicitly deferred them.

See [gap-batch.md](gap-batch.md) for the verify question shape.

## Taxonomy (category + id prefix)

| SRS portion | `category` | Id prefix | Knowledge file (preferred) | Graph label |
| --- | --- | --- | --- | --- |
| Product function / feature | `feature` | `FEAT` | `knowledge/features.yaml` | `Feature` |
| Business / user goal | `goal` | `GOAL` | `knowledge/goals.yaml` | `Goal` |
| Functional requirement | `functional` | `REQ` | `knowledge/requirements.yaml` | `Requirement` |
| Business rule / policy | `constraint` | `BR` | `knowledge/business-rules.yaml` | `Constraint` |
| Limitation | `limitation` | `LIM` | `knowledge/business-rules.yaml` or `limitations.yaml` | `Limitation` |
| Assumption | `assumption` | `ASM` | `knowledge/assumptions.yaml` | `Assumption` |
| Dependency | `dependency` | `DEP` | `knowledge/assumptions.yaml` or `dependencies.yaml` | `Dependency` |
| Workflow / operational path | `workflow` | `WF` | `knowledge/workflows.yaml` | `Task` |
| Use case / user journey | `use_case` | `UC` | `knowledge/use-cases.yaml` or `workflows.yaml` | `UseCase` |
| External interface | `interface` | `IF` | `knowledge/interfaces.yaml` | `ExternalInterface` |
| Logical data / entity | `data` | `DATA` | `knowledge/data.yaml` | `DataEntity` |
| Performance NFR | `performance` | `PERF` | `knowledge/quality.yaml` | `PerformanceRequirement` |
| Usability NFR | `usability` | `USE` | `knowledge/quality.yaml` | `UsabilityRequirement` |
| Security / privacy NFR | `security` | `SEC` | `knowledge/quality.yaml` | `QualityAttribute` |
| Other quality attribute | `quality` / `non_functional` | `NFR` | `knowledge/quality.yaml` | `QualityAttribute` |
| Design constraint / platform | `design_constraint` | `DES` | `knowledge/business-rules.yaml` | `DesignConstraint` |
| Standards compliance | `standard` | `STD` | `knowledge/quality.yaml` | `Standard` |
| Verification method | `verification` | `VER` | `knowledge/verification.yaml` | `VerificationMethod` |
| Glossary term | `glossary` | `GLOSS` | `knowledge/glossary.yaml` | `GlossaryTerm` |
| External reference | `reference` | `REF` | `knowledge/references.yaml` | `Reference` |
| Context / as-is pain | `contextual` | `REQ` or `CTX` | `knowledge/requirements.yaml` | `RequirementNode` |

Id form: `<SLUG_PREFIX>-<PREFIX>-NNN` (e.g. `LIB-FEAT-001`, `LIB-GOAL-001`).

## Trace links (required when both ends exist)

On `KnowledgeFact`, set optional lists (empty by default):

| Field | Meaning | Typical use |
| --- | --- | --- |
| `satisfies_ids` | This FR/NFR supports a Feature | `REQ` → `FEAT` |
| `derives_from_ids` | This requirement serves a Goal | `REQ` → `GOAL` |
| `depends_on_ids` | Hard dependency on another fact | `REQ`/`FEAT` → `DEP` or another `REQ` |

Graph edges created on reindex: `SATISFIES`, `DERIVES_FROM`, `DEPENDS_ON`.

Every in-scope `REQ` should `satisfies_ids` at least one `FEAT` once Features are prescribed (or a deferred verify gap explains why not).

## What to prescribe (create) / audit (depth-update)

Aim for **at least one** record in these buckets unless the instructor explicitly defers them. Prefer prescribe-by-default when reasonably inferable:

1. **Goals** — why the system exists (stakeholder outcomes)
2. **Features** — named product capabilities students can discover
3. **Functional requirements** — linked to features via `satisfies_ids`
4. **Assumptions** — structural ones as `clarified` prescriptions until verified; then optional `assumed` + decision
5. **Dependencies** — external systems, data feeds, org processes
6. **Interfaces** — user / software / communications (and hardware if relevant)
7. **Data entities** — core records the system stores or exchanges
8. **Use cases or workflows** — happy path + exception; prefer `UC` when actor+goal+flow are clear
9. **Quality** — performance, security/privacy, usability where cues or brief support them
10. **Verification** — method hints (`test` / `demo` / `analysis` / `inspection`) for high-value FRs when testability is implied
11. **Glossary / references** — only when terms or external docs matter for elicitation

## Promote-from-existing (before inventing)

| Existing pattern | Promote to |
| --- | --- |
| `ASM-*` with `category: constraint` | `category: assumption` (keep id); graph → `Assumption` |
| Functional `REQ-*` that name a product capability | Split: add `FEAT-*` summary + keep `REQ-*` with `satisfies_ids: [FEAT-…]` |
| `WF-*` that are full actor journeys | Add sibling `UC-*` **or** retag `category: use_case` only if the statement is use-case shaped |
| Privacy/encryption/trust `REQ`/`NFR` | `category: security` or `quality` |
| “Must integrate with X” statements | `DEP-*` + `depends_on_ids` on consumers |

## Scenario brief (`scenario.yaml`)

Populate SRS intro-ish fields in the brief (still one string): purpose, in-scope / out-of-scope, and primary users. Optional structured notes may go in `source_notes`. Dedicated `Purpose`/`Scope` graph nodes are not required if the brief is explicit.

## Ask-first themes (not prescribe-by-default)

Reserve classic gap batches (≤ 5) for non-inferable policy:

- Exact numeric caps, windows, SLAs
- Who wins when roles conflict
- What must remain unknown for graded elicitation
- Sensitive retention / legal claims without cue support

Still ≤ **five** questions per batch. See [gap-batch.md](gap-batch.md).
