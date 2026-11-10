# Instructor-private materials

Authoritative defect manifests and hidden regression tests for COMP 3613 flawed starters.

This tree is the **canonical SoT inside sellm** — sellm does not read `seproject/instructor/` at runtime or authoring time. Runtime judge packs derived from these manifests live in `app/examiner/knowledge/`.

**Never** copy these into `templates/<slug>/`, student remotes, or student-facing prompts.

| Path | Purpose |
| --- | --- |
| `private/<slug>/defect-manifest.yaml` | Seeded defects, severity, evidence, intended design-pattern fix |
| `private/<slug>/tests/test_seeded_defects.py` | Hidden checks against sibling `templates/<slug>/` |
| `../app/examiner/knowledge/<slug>.yaml` | Runtime judge gold derived from these manifests |

## Run hidden defect tests

Requires a sibling checkout of [comp3613-templates](https://github.com/Snickdx/comp3613-templates) at `../templates`.

```powershell
cd ..\templates\job-board
pip install -r requirements.txt
python -m pytest ..\..\sellm\instructor\private\job-board\tests -q
```

## Sync into examiner knowledge packs

After editing a manifest, update `app/examiner/knowledge/<slug>.yaml`
(`intended_pattern`, `architecture_defect`, `defects`, `focus_paths`, `judge_concepts`).
The exit-interview scorer loads those packs — not the raw manifests — at finish time.
