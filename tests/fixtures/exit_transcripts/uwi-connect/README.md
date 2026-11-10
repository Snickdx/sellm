# Campus networking / info sharing exit-interview transcript bands

See [`bands.yaml`](bands.yaml). Shared runner: `tests/test_exit_transcript_bands.py`.

```powershell
$env:RAG_BACKEND='none'
python -m pytest tests/test_exit_transcript_bands.py -q -k uwi-connect
python -m tests.fixtures.exit_transcripts.render_bands --scenario uwi-connect --write
```
