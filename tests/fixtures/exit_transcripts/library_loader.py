"""Back-compat wrappers for library transcript fixtures."""

from __future__ import annotations

from tests.fixtures.exit_transcripts.bands_loader import (
    build_band_bundle as _build,
    load_bands,
    render_band_transcript as _render,
)


def load_library_bands():
    return load_bands("library")


def build_band_bundle(band_key: str):
    return _build("library", band_key)


def render_band_transcript(band_key: str) -> str:
    return _render("library", band_key)
