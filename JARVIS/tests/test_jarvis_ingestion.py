from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook

from jarvis.ingestion.archives import ArchiveSafetyError, extract_archive
from jarvis.ingestion.parsers import parse_document
from jarvis.ingestion.repository import analyze_code


def test_docx_heading_and_text_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_heading("Plan", level=1)
    document.add_paragraph("Prepare the first topic.")
    document.save(path)

    parsed = parse_document(path)
    assert [unit.text for unit in parsed.units] == ["Plan", "Prepare the first topic."]
    assert parsed.units[1].heading == "Plan"


def test_xlsx_citation_uses_real_column_letters(tmp_path: Path) -> None:
    path = tmp_path / "wide.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["AA2"] = "value"
    workbook.save(path)

    parsed = parse_document(path)
    assert parsed.units[0].sheet == "Sheet"
    assert parsed.units[0].cell_range == "A1:AA2"


def test_zip_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../escape.txt", "not allowed")

    with pytest.raises(ArchiveSafetyError):
        extract_archive(archive, tmp_path / "out", max_files=10, max_extracted_bytes=1024)
    assert not (tmp_path / "escape.txt").exists()


def test_nested_archive_is_not_expanded(tmp_path: Path) -> None:
    nested_bytes = io.BytesIO()
    with zipfile.ZipFile(nested_bytes, "w") as nested:
        nested.writestr("inside.txt", "nested")
    archive = tmp_path / "outer.zip"
    with zipfile.ZipFile(archive, "w") as outer:
        outer.writestr("readme.txt", "safe")
        outer.writestr("nested.zip", nested_bytes.getvalue())

    extracted = extract_archive(
        archive, tmp_path / "out", max_files=10, max_extracted_bytes=1024 * 1024
    )
    assert [path.name for path in extracted] == ["readme.txt"]
    assert not (tmp_path / "out" / "nested.zip").exists()


def test_repository_fallback_extracts_symbols_and_imports(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    text = "import json\n\nclass Service:\n    def run(self):\n        return json.dumps({})\n"
    symbols, edges = analyze_code(path, text)
    names = {symbol.name for symbol in symbols}
    assert {"Service", "run"}.issubset(names)
    assert any(edge.target_ref == "json" for edge in edges)
