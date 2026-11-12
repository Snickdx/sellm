# IEEE / ISO/IEC/IEEE 29148 SRS coverage in scenario packages

Author knowledge so the package can populate a domain graph close to an SRS
outline (29148 §9.6 / classic IEEE 830). Do **not** invent transcript quotes;
use `confirmed` only with cues, otherwise instructor `clarified` / `assumed`.

Canonical gap list also lives in `docs/YAML_GRAPH_MODEL.md`.

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

Every `REQ` that is in-scope for the graded MVP should eventually `satisfies_ids` at least one `FEAT` (or an instructor gap explains why not).

## What to extract (create) / audit (depth-update)

For each package, aim for **at least one** record (confirmed or instructor-approved) in these buckets unless the instructor explicitly defers them:

1. **Goals** — why the system exists (stakeholder outcomes)
2. **Features** — named product capabilities students can discover
3. **Functional requirements** — linked to features via `satisfies_ids`
4. **Assumptions** — only with decision provenance (`ASM-*`, `category: assumption`)
5. **Dependencies** — external systems, data feeds, org processes
6. **Interfaces** — user / software / communications (and hardware if relevant)
7. **Data entities** — core records the system stores or exchanges
8. **Use cases or workflows** — happy path + exception; prefer `UC` when actor+goal+flow are clear
9. **Quality** — performance, security/privacy, usability where the transcript or instructor supplies them
10. **Verification** — method hints (`test` / `demo` / `analysis` / `inspection`) tied to high-value FRs when known
11. **Glossary / references** — only when terms or external docs matter for elicitation

## Promote-from-existing (before inventing)

When deepening a thin package, **remap first**:

| Existing pattern | Promote to |
| --- | --- |
| `ASM-*` with `category: constraint` | `category: assumption` (keep id); graph → `Assumption` |
| Functional `REQ-*` that name a product capability | Split: add `FEAT-*` summary + keep `REQ-*` with `satisfies_ids: [FEAT-…]` |
| `WF-*` that are full actor journeys | Add sibling `UC-*` **or** retag `category: use_case` only if the statement is use-case shaped |
| Privacy/encryption/trust `REQ`/`NFR` | `category: security` or `quality` |
| “Must integrate with X” statements | `DEP-*` + `depends_on_ids` on consumers |

Do **not** fabricate Features/Goals from thin air — draft gap questions with suggested assumptions.

## Scenario brief (`scenario.yaml`)

Populate SRS intro-ish fields in the brief (still one string): purpose, in-scope / out-of-scope, and primary users. Optional structured notes may go in `source_notes`. Dedicated `Purpose`/`Scope` graph nodes are not required if the brief is explicit.

## Gap-batch themes for SRS holes

When coverage is missing, prefer instructor questions that unlock:

- Named product features vs laundry-list FRs
- Top goals / success outcomes
- External systems and interfaces
- Core data entities and retention/visibility
- Assumptions vs hard constraints vs dependencies
- How critical FRs would be verified

Still ≤ **five** questions per batch. See [gap-batch.md](gap-batch.md).
