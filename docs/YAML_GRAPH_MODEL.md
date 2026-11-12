# YAML scenario graph model (Neo4j)

Generalized graph used by **neo4j** / **hybrid** modes when a YAML scenario + persona is selected. Excel RAG nodes remain separate; reindex replaces only `Yaml*` labels.

## Node types

| Label | Key | Purpose |
| --- | --- | --- |
| `YamlScenario` | `slug` + `version` | Package root (title, brief, status) |
| `YamlPersona` | `key` + scenario | Chat stakeholder; carries `system_role` / capability list props |
| `YamlFact` | `node_id` (`yaml:{slug}:{fact_id}`) | Student-visible knowledge (embedded for vector search) |
| `YamlSystemRole` | `name` | Shared vocabulary: `platform_admin`, `operator`, `approver`, `end_user`, `hybrid` |
| `YamlCapability` | `name` | Shared admin capability verbs (`publish_listings`, …) |
| `YamlDecision` | `decision_id` + scenario | Instructor gap decision that produced facts |
| `YamlSourceCue` | `cue_id` + `file` + scenario | Transcript provenance for confirmed/clarified facts |

Instructor-only `gaps.yaml` open questions and `evaluation.yaml` are **not** indexed.

## Relationships

| Type | From → To | Meaning |
| --- | --- | --- |
| `HAS_PERSONA` | Scenario → Persona | Persona belongs to package |
| `HAS_FACT` | Scenario → Fact | Fact belongs to package |
| `HAS_DECISION` | Scenario → Decision | Decision recorded for package |
| `KNOWS` | Persona → Fact | Persona may disclose this fact |
| `HAS_ROLE` | Persona → SystemRole | In-system authority class |
| `CAN` | Persona → Capability | Concrete admin verb |
| `FROM_DECISION` | Fact → Decision | Fact provenance via gap decision |
| `PRODUCED` | Decision → Fact | Inverse of `FROM_DECISION` |
| `CITED_FROM` | Fact → SourceCue | Transcript cue citation |

## Visual map (node types + relationships)

```mermaid
flowchart LR
    classDef pkg fill:#eef2ff,stroke:#4f46e5,color:#111827,stroke-width:1px;
    classDef actor fill:#ecfeff,stroke:#0891b2,color:#111827,stroke-width:1px;
    classDef knowledge fill:#f0fdf4,stroke:#16a34a,color:#111827,stroke-width:1px;
    classDef governance fill:#fff7ed,stroke:#ea580c,color:#111827,stroke-width:1px;
    classDef provenance fill:#fdf2f8,stroke:#db2777,color:#111827,stroke-width:1px;

    SC["YamlScenario<br/>key: slug + version"]:::pkg
    PE["YamlPersona<br/>key: key + scenario"]:::actor
    FA["YamlFact<br/>key: yaml:{slug}:{fact_id}"]:::knowledge
    SR["YamlSystemRole<br/>key: name"]:::governance
    CP["YamlCapability<br/>key: name"]:::governance
    DE["YamlDecision<br/>key: decision_id + scenario"]:::provenance
    CU["YamlSourceCue<br/>key: cue_id + file + scenario"]:::provenance

    SC -- HAS_PERSONA --> PE
    SC -- HAS_FACT --> FA
    SC -- HAS_DECISION --> DE
    PE -- KNOWS --> FA
    PE -- HAS_ROLE --> SR
    PE -- CAN --> CP
    FA -- FROM_DECISION --> DE
    DE -- PRODUCED --> FA
    FA -- CITED_FROM --> CU
```

## Reindex

```bash
python scripts/reindex_scenarios.py
# or POST /api/admin/scenarios/reindex
```
