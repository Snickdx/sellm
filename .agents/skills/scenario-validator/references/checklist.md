# Scenario validation checklist

## Schema / IDs

- [ ] `scenario.yaml` has slug, title, version, status, brief
- [ ] All fact IDs unique across knowledge files
- [ ] Persona IDs unique; filenames match `id` where practical
- [ ] Enum values match app schema (`status`, `origin`, `disclosure`, `category`)

## Provenance

- [ ] `confirmed` + `origin: transcript` ⇒ non-empty `source_refs`
- [ ] Each `source_refs` cue_id exists in `normalized/cues.jsonl` (or sources parse cleanly)
- [ ] `assumed` ⇒ instructor approval fields present
- [ ] No silent speaker attribution without `speaker_confidence` flags on ambiguous cues

## Persona scope

- [ ] `known_fact_ids` ⊆ declared fact IDs
- [ ] Uncertainty / referral rules present
- [ ] Roles are fictionalized (not real interviewee names)
- [ ] System operators have `system_role` + `admin_capabilities` when they administer the product

## Instructor-only

- [ ] `gaps.yaml` and `evaluation.yaml` exist for complete packages
- [ ] Student import/runtime paths exclude those files from LLM prompts and student APIs

## Simulation smoke

- [ ] Known fact answered consistently under paraphrase
- [ ] Unknown topic → uncertainty or referral, not invented policy
- [ ] Attempt to extract hidden rubric → refused / no leak

## Multi-mode sync

- [ ] YAML package loads into registry
- [ ] Vector index refreshed (or reindex scheduled) after persona/fact edits
- [ ] Neo4j graph refreshed after persona/fact edits
- [ ] Direct/yaml preprompt pack reflects `system_role` / admin fields when present
