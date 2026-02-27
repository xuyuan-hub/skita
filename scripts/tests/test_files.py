"""scripts/files.py 单元测试"""

from pathlib import Path

import pytest

import scripts.files as files_mod
from scripts.files import Files


@pytest.fixture
def isolated_files(tmp_path, monkeypatch):
    """用 tmp_path 隔离文件存储目录"""
    files_root = tmp_path / "files"
    exports_root = tmp_path / "exports"
    files_root.mkdir()
    exports_root.mkdir()
    monkeypatch.setattr(files_mod, "FILES_ROOT", files_root)
    monkeypatch.setattr(files_mod, "EXPORTS_ROOT", exports_root)
    return Files(), files_root, exports_root


@pytest.fixture
def sample_file(tmp_path):
    """创建测试源文件"""
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    return f


class TestSave:
    def test_save_creates_file(self, isolated_files, sample_file):
        fs, files_root, _ = isolated_files
        result = fs.save(str(sample_file), category="test")

        assert result["reused"] is False
        assert result["size"] > 0
        # 文件存在于 test/<YYYY-MM>/ 目录下
        saved = files_root / result["relative_path"]
        assert saved.exists()
        assert saved.read_text() == "hello world"

    def test_save_dedup(self, isolated_files, sample_file):
        fs, _, _ = isolated_files
        r1 = fs.save(str(sample_file), category="test")
        r2 = fs.save(str(sample_file), category="test")

        assert r1["relative_path"] == r2["relative_path"]
        assert r2["reused"] is True

    def test_save_collision(self, isolated_files, tmp_path):
        fs, files_root, _ = isolated_files

        # 创建两个同名但内容不同的文件
        f1 = tmp_path / "src1" / "data.txt"
        f1.parent.mkdir()
        f1.write_text("content A", encoding="utf-8")

        f2 = tmp_path / "src2" / "data.txt"
        f2.parent.mkdir()
        f2.write_text("content B", encoding="utf-8")

        r1 = fs.save(str(f1), category="test")
        r2 = fs.save(str(f2), category="test")

        # 路径不同
        assert r1["relative_path"] != r2["relative_path"]
        assert r2["reused"] is False

    def test_save_source_not_found(self, isolated_files):
        fs, _, _ = isolated_files
        with pytest.raises(FileNotFoundError, match="源文件不存在"):
            fs.save("/nonexistent/file.txt", category="test")


class TestRead:
    def test_abs_path(self, isolated_files):
        fs, files_root, _ = isolated_files
        p = fs.abs_path("test/2026-02/file.txt")
        assert p == files_root / "test" / "2026-02" / "file.txt"

    def test_read_text(self, isolated_files, sample_file):
        fs, _, _ = isolated_files
        result = fs.save(str(sample_file), category="test")
        content = fs.read_text(result["relative_path"])
        assert content == "hello world"

    def test_read_text_not_found(self, isolated_files):
        fs, _, _ = isolated_files
        with pytest.raises(FileNotFoundError, match="文件不存在"):
            fs.read_text("nonexistent/path.txt")


class TestList:
    def test_list_category(self, isolated_files, sample_file):
        fs, _, _ = isolated_files
        fs.save(str(sample_file), category="mycat")
        items = fs.list("mycat")
        assert len(items) == 1
        assert items[0]["filename"] == "sample.txt"

    def test_list_empty(self, isolated_files):
        fs, _, _ = isolated_files
        assert fs.list("nonexistent") == []


class TestExport:
    def test_save_export(self, isolated_files):
        fs, _, exports_root = isolated_files
        path = fs.save_export("exported data", "report.csv")
        assert path == exports_root / "report.csv"
        assert path.read_text(encoding="utf-8") == "exported data"
