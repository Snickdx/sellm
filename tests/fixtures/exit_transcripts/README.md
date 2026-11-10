# Exit-interview transcript bands

Synthetic Q/A answers for calibrating the provisional exit-interview scorer on each
COMP 3613 scenario. Each slug has `low` / `mid` / `high` bands.

| Band | Intent | Typical provisional score |
| --- | --- | ---: |
| `low` | Evasive / no ownership | 1–2 |
| `mid` | Verbose but avoids gold pattern/defect terms | 3–4 |
| `high` | Names intended pattern, defects, focus files | 5 |

## Layout

```
exit_transcripts/
  <slug>/bands.yaml
  <slug>/transcript_{low,mid,high}.md
  bands_loader.py
  render_bands.py
```

## Commands

```powershell
$env:RAG_BACKEND='none'
python -m pytest tests/test_exit_transcript_bands.py -q
python -m tests.fixtures.exit_transcripts.render_bands --write
python scripts/gen_exit_transcript_bands.py --write --validate --render
```
