from __future__ import annotations

from pathlib import Path

import pytest

from app.services.dataset_schema import detect_dataset


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_detect_actions(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "actions.csv",
        "78fedfdf13fc820e363e39986ff91e94,03c6699ea836decbc5c8fc2dbae7bd3b,"
        "1426406400,1,20150315\n",
    )
    spec = detect_dataset(path)
    assert spec.kind == "actions"
    assert spec.columns == [
        "user_id",
        "song_id",
        "gmt_create",
        "action_type",
        "Ds",
    ]
    assert spec.has_header is False


def test_detect_songs(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "songs.csv",
        "03c6699ea836decbc5c8fc2dbae7bd3b,c81f89cf7edd24930641afa2e411b09c,"
        "20110910,100,1,1\n",
    )
    spec = detect_dataset(path)
    assert spec.kind == "songs"
    assert spec.columns[2] == "publish_time"


def test_detect_generic_with_header(tmp_path: Path) -> None:
    path = _write(tmp_path, "sales.csv", "date,region,amount\n2025-01-01,east,10\n")
    spec = detect_dataset(path)
    assert spec.kind == "generic"
    assert spec.has_header is True
    assert spec.columns == ["date", "region", "amount"]


def test_detect_generic_headerless(tmp_path: Path) -> None:
    path = _write(tmp_path, "plain.csv", "1,2,3\n4,5,6\n")
    spec = detect_dataset(path)
    assert spec.kind == "generic"
    assert spec.has_header is False
    assert spec.columns == ["col_1", "col_2", "col_3"]


def test_empty_file_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.csv", "")
    with pytest.raises(ValueError):
        detect_dataset(path)
