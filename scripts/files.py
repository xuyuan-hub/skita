"""
scripts/files.py
本地文件存储管理。

用法：
    from scripts.files import Files
    f = Files()
    result = f.save("/path/to/raw.csv", category="pcr")
    # result["relative_path"] → 存入数据库的路径
"""

import shutil
import hashlib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
FILES_ROOT = ROOT / "data" / "files"
EXPORTS_ROOT = ROOT / "data" / "exports"


class Files:
    def __init__(self):
        FILES_ROOT.mkdir(parents=True, exist_ok=True)
        EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    def save(self, source_path: str, category: str, filename: str = None) -> dict:
        """
        将文件复制到 data/files/<category>/<YYYY-MM>/ 目录。
        如果文件内容完全相同（hash 相同），跳过复制直接返回已有路径。
        返回 relative_path（相对于 data/files/），存入数据库。
        """
        source = Path(source_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        target_name = filename or source.name
        date_dir = datetime.now().strftime("%Y-%m")
        target_dir = FILES_ROOT / category / date_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / target_name

        # 重名但内容不同：加时间戳后缀
        if target.exists():
            if _md5(source) == _md5(target):
                # 完全相同，直接复用
                return {
                    "relative_path": str(target.relative_to(FILES_ROOT)),
                    "reused": True,
                    "size": target.stat().st_size,
                }
            ts = datetime.now().strftime("%H%M%S")
            target = target_dir / f"{source.stem}_{ts}{source.suffix}"

        shutil.copy2(source, target)
        return {
            "relative_path": str(target.relative_to(FILES_ROOT)),
            "absolute_path": str(target),
            "reused": False,
            "size": target.stat().st_size,
        }

    def abs_path(self, relative_path: str) -> Path:
        """将数据库中存的相对路径还原为绝对路径"""
        return FILES_ROOT / relative_path

    def read_text(self, relative_path: str, encoding: str = "utf-8") -> str:
        p = self.abs_path(relative_path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {relative_path}")
        return p.read_text(encoding=encoding)

    def list(self, category: str = "") -> list[dict]:
        base = FILES_ROOT / category if category else FILES_ROOT
        if not base.exists():
            return []
        return [
            {
                "relative_path": str(f.relative_to(FILES_ROOT)),
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            }
            for f in sorted(base.rglob("*")) if f.is_file()
        ]

    def save_export(self, content: str, filename: str) -> Path:
        """保存导出文件到 data/exports/，返回绝对路径"""
        target = EXPORTS_ROOT / filename
        target.write_text(content, encoding="utf-8")
        return target


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    import sys, json
    f = Files()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        cat = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(f.list(cat), ensure_ascii=False, indent=2))
    elif cmd == "save":
        result = f.save(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False, indent=2))
