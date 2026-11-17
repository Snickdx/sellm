"""Excel export mirrors YAML packages without being a runtime dependency."""

from pathlib import Path

from app.scenarios.excel_export import build_workbook_frames, export_package_to_excel
from app.scenarios.loader import load_scenario_package


def test_export_library_workbook(tmp_path: Path):
    package = load_scenario_package(Path("scenarios/library"))
    frames = build_workbook_frames(package)
    assert "Project" in frames
    assert "Stakeholder" in frames
    assert "Relationships" in frames
    assert not frames["Project"].empty
    assert not frames["Stakeholder"].empty

    out = export_package_to_excel(package, tmp_path / "library-workbook.xlsx")
    assert out.is_file()
    assert out.stat().st_size > 0
