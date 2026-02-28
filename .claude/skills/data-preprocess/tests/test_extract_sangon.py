#!/usr/bin/env python3
"""
生工引物订购表提取脚本测试

测试数据: tests/data/引物订购表-26-01-12.xlsx
运行: python -m pytest .claude/skills/data-preprocess/tests/test_extract_sangon.py -v
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "data-preprocess" / "scripts"))

from extract_sangon_order_xlsx import PrimerOrderExtractor

TEST_DATA = Path(__file__).parent / "data" / "引物订购表-26-01-12.xlsx"


@pytest.fixture
def extractor():
    return PrimerOrderExtractor(str(TEST_DATA))


@pytest.fixture
def extracted_data(extractor):
    return extractor.extract_all()


# ── 基本提取 ──────────────────────────────────────────────────────────────────

class TestExtractAll:
    def test_returns_dict_with_required_keys(self, extracted_data):
        assert "order_info" in extracted_data
        assert "primer_data" in extracted_data

    def test_order_info_is_dict(self, extracted_data):
        assert isinstance(extracted_data["order_info"], dict)

    def test_primer_data_is_list(self, extracted_data):
        assert isinstance(extracted_data["primer_data"], list)


# ── 订单信息 ──────────────────────────────────────────────────────────────────

class TestOrderInfo:
    def test_customer_name(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("customer_name") is not None
        assert len(info["customer_name"]) > 0

    def test_customer_phone(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("customer_phone") == "15186909733"

    def test_customer_email(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("customer_email") == "2827883762@qq.com"

    def test_payment_method(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("payment_method") is not None

    def test_boolean_fields(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("invoice_with_goods") is True
        assert info.get("weekend_delivery") is True
        assert info.get("partial_delivery") is True

    def test_company_name(self, extracted_data):
        info = extracted_data["order_info"]
        assert info.get("company_name") is not None


# ── 引物数据 ──────────────────────────────────────────────────────────────────

class TestPrimerData:
    def test_primer_count(self, extracted_data):
        assert len(extracted_data["primer_data"]) == 3

    def test_primer_has_name(self, extracted_data):
        for primer in extracted_data["primer_data"]:
            assert "primer_name" in primer
            assert primer["primer_name"]

    def test_primer_has_sequence(self, extracted_data):
        for primer in extracted_data["primer_data"]:
            assert "sequence" in primer
            assert len(primer["sequence"]) > 0

    def test_base_count_matches_sequence(self, extracted_data):
        for primer in extracted_data["primer_data"]:
            assert primer["base_count"] == len(primer["sequence"])

    def test_first_primer_values(self, extracted_data):
        p = extracted_data["primer_data"][0]
        assert p["primer_name"] == "ZQ0722F34"
        assert p["sequence"] == "ggggatcgatcctttagcgg"
        assert p["base_count"] == 20
        assert p["purification_method"] == "HAP"

    def test_primer_modifications(self, extracted_data):
        p = extracted_data["primer_data"][0]
        assert p.get("five_modification") == "5`6-FAM"
        assert p.get("three_modification") == "3`Acrydite"

    def test_primer_type(self, extracted_data):
        types = [p.get("primer_type") for p in extracted_data["primer_data"]]
        assert all(t is not None for t in types)


# ── JSON 导出 ─────────────────────────────────────────────────────────────────

class TestJsonExport:
    def test_save_to_json(self, extractor):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name

        data = extractor.save_to_json(tmp_path)
        saved = json.loads(Path(tmp_path).read_text(encoding="utf-8"))

        assert saved["order_info"] == data["order_info"]
        assert len(saved["primer_data"]) == len(data["primer_data"])

        Path(tmp_path).unlink(missing_ok=True)


# ── 数据库存储 ────────────────────────────────────────────────────────────────

class TestSaveToDB:
    def test_save_to_db_returns_id(self, extractor):
        """测试存入数据库并验证可查询"""
        data = extractor.extract_all()
        row_id = extractor.save_to_db(data)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_saved_record_queryable(self, extractor):
        """验证存入的记录可以从数据库查询到"""
        from scripts.db import DB

        data = extractor.extract_all()
        row_id = extractor.save_to_db(data)

        db = DB()
        record = db.query_one(
            "SELECT * FROM data_sangon_primer_order WHERE id = ?", [row_id]
        )
        assert record is not None
        assert record["primer_count"] == 3
        assert record["customer_phone"] is not None

        # 验证 primer_data 是合法 JSON
        primers = json.loads(record["primer_data"])
        assert len(primers) == 3
        assert primers[0]["primer_name"] == "ZQ0722F34"
