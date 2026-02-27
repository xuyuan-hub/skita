"""scripts/db.py 单元测试"""

import json
import shutil
from pathlib import Path

import pytest

from scripts.db import DB


@pytest.fixture
def test_meta(tmp_path):
    """在 tmp 目录创建测试用 schema 文件"""
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    schema = {
        "display_name": "测试表",
        "description": "单元测试专用",
        "version": 1,
        "fields": [
            {"name": "name", "type": "text", "required": True},
            {"name": "score", "type": "number", "required": True},
            {"name": "active", "type": "boolean", "required": False},
            {"name": "tags", "type": "json", "required": False},
            {"name": "note", "type": "text", "required": False},
        ],
    }
    (meta_dir / "test_item.json").write_text(json.dumps(schema), encoding="utf-8")
    return meta_dir


@pytest.fixture
def db(tmp_path, test_meta, monkeypatch):
    """创建隔离的测试数据库"""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("scripts.db.META_DIR", test_meta)
    return DB(path=db_path)


class TestInit:
    def test_init_creates_system_tables(self, db):
        tables = {
            r["name"]
            for r in db.query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "_meta_schemas" in tables
        assert "_recycle_bin" in tables
        assert "_sync_log" in tables


class TestEnsureTable:
    def test_creates_table(self, db):
        table = db.ensure_table("test_item")
        assert table == "data_test_item"
        cols = {r["name"] for r in db.query("PRAGMA table_info(data_test_item)")}
        assert {"id", "created_at", "updated_at", "name", "score", "active", "tags", "note"} <= cols

    def test_migration_adds_column(self, db, test_meta):
        db.ensure_table("test_item")

        # 给 schema 加一个新字段
        schema_path = test_meta / "test_item.json"
        schema = json.loads(schema_path.read_text())
        schema["fields"].append({"name": "extra", "type": "text", "required": False})
        schema_path.write_text(json.dumps(schema))

        db.ensure_table("test_item")
        cols = {r["name"] for r in db.query("PRAGMA table_info(data_test_item)")}
        assert "extra" in cols


class TestCRUD:
    def test_insert_and_query(self, db):
        db.ensure_table("test_item")
        row_id = db.insert("data_test_item", {"name": "Alice", "score": 95.5})
        assert row_id >= 1

        rows = db.query("SELECT * FROM data_test_item WHERE id = ?", [row_id])
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"
        assert rows[0]["score"] == 95.5

    def test_query_one(self, db):
        db.ensure_table("test_item")
        db.insert("data_test_item", {"name": "Bob", "score": 80})

        row = db.query_one("SELECT * FROM data_test_item WHERE name = ?", ["Bob"])
        assert row is not None
        assert row["name"] == "Bob"

        none_row = db.query_one("SELECT * FROM data_test_item WHERE name = ?", ["Nobody"])
        assert none_row is None

    def test_update(self, db):
        db.ensure_table("test_item")
        row_id = db.insert("data_test_item", {"name": "Carol", "score": 70})

        affected = db.update("data_test_item", {"score": 90}, "id = ?", [row_id])
        assert affected == 1

        row = db.query_one("SELECT * FROM data_test_item WHERE id = ?", [row_id])
        assert row["score"] == 90

    def test_delete_soft(self, db):
        db.ensure_table("test_item")
        row_id = db.insert("data_test_item", {"name": "Dave", "score": 60})

        deleted = db.delete("data_test_item", "id = ?", [row_id])
        assert deleted == 1

        # 原表无数据
        assert db.query_one("SELECT * FROM data_test_item WHERE id = ?", [row_id]) is None

        # 回收站有记录
        bin_rows = db.query("SELECT * FROM _recycle_bin WHERE source_table = 'data_test_item'")
        assert len(bin_rows) >= 1
        restored = json.loads(bin_rows[-1]["row_json"])
        assert restored["name"] == "Dave"

    def test_list_schemas(self, db):
        db.ensure_table("test_item")
        schemas = db.list_schemas()
        names = [s["name"] for s in schemas]
        assert "test_item" in names


class TestValidation:
    def test_validates_required_field(self, db):
        db.ensure_table("test_item")
        with pytest.raises(ValueError, match="缺少必填字段: name"):
            db.insert("data_test_item", {"score": 50})

    def test_validates_required_none(self, db):
        db.ensure_table("test_item")
        with pytest.raises(ValueError, match="缺少必填字段: name"):
            db.insert("data_test_item", {"name": None, "score": 50})

    def test_validates_number_type(self, db):
        db.ensure_table("test_item")
        with pytest.raises(ValueError, match="字段 score 应为数字"):
            db.insert("data_test_item", {"name": "Test", "score": "not_a_number"})

    def test_validates_boolean_type(self, db):
        db.ensure_table("test_item")
        with pytest.raises(ValueError, match="字段 active 应为布尔值"):
            db.insert("data_test_item", {"name": "Test", "score": 80, "active": "yes"})

    def test_validates_json_field(self, db):
        db.ensure_table("test_item")
        with pytest.raises(ValueError, match="不是合法 JSON"):
            db.insert("data_test_item", {"name": "Test", "score": 80, "tags": "{bad json"})

    def test_valid_data_passes(self, db):
        db.ensure_table("test_item")
        row_id = db.insert("data_test_item", {
            "name": "Valid",
            "score": 100,
            "active": 1,
            "tags": '["a", "b"]',
            "note": "ok",
        })
        assert row_id >= 1
