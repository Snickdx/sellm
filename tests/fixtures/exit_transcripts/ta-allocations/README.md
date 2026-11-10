# TA allocation exit-interview transcript bands

See [`bands.yaml`](bands.yaml). Shared runner: `tests/test_exit_transcript_bands.py`.

```powershell
$env:RAG_BACKEND='none'
python -m pytest tests/test_exit_transcript_bands.py -q -k ta-allocations
python -m tests.fixtures.exit_transcripts.render_bands --scenario ta-allocations --write
```
