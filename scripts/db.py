"""
scripts/db.py
本地 SQLite 操作工具。Claude Code 可直接 import 或 subprocess 调用。

用法：
    from scripts.db import DB
    db = DB()
    db.ensure_table("pcr_result")
    db.insert("data_pcr_result", {"sample_id": "S001", ...})
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "skita.db"
META_DIR = ROOT / "meta"

# SQLite 字段类型映射
FIELD_TYPE_MAP = {
    "text":      "TEXT",
    "number":    "REAL",
    "date":      "TEXT",
    "boolean":   "INTEGER",
    "file_path": "TEXT",
    "json":      "TEXT",
}

logger = logging.getLogger(__name__)


class DB:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    # ── 连接 ──────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self):
        """初始化系统表"""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS _meta_schemas (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    description  TEXT DEFAULT '',
                    version      INTEGER DEFAULT 1,
                    schema_json  TEXT NOT NULL,
                    created_at   TEXT DEFAULT (datetime('now')),
                    updated_at   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS _recycle_bin (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT NOT NULL,
                    source_id    INTEGER NOT NULL,
                    row_json     TEXT NOT NULL,
                    deleted_at   TEXT DEFAULT (datetime('now')),
                    deleted_by   TEXT DEFAULT 'claude'
                );

                CREATE TABLE IF NOT EXISTS _sync_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    action       TEXT NOT NULL,
                    schema_name  TEXT,
                    local_id     INTEGER,
                    central_id   TEXT,
                    status       TEXT NOT NULL,
                    message      TEXT DEFAULT '',
                    executed_at  TEXT DEFAULT (datetime('now'))
                );
            """)

    # ── 基础 CRUD ─────────────────────────────────────────────────────────────

    def query(self, sql: str, params: list = None) -> list[dict]:
        """执行查询，返回字典列表"""
        with self._conn() as conn:
            cursor = conn.execute(sql, params or [])
            return [dict(row) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: list = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, data: dict) -> int:
        """插入记录，返回新行 id。自动校验 schema 约束。"""
        self._validate(table, data)
        data = {**data, "created_at": data.get("created_at", _now())}
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            cursor = conn.execute(sql, list(data.values()))
            conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: dict, where: str, where_params: list = None) -> int:
        """更新记录，返回受影响行数"""
        data = {**data, "updated_at": _now()}
        set_clause = ", ".join([f"{k} = ?" for k in data])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        with self._conn() as conn:
            cursor = conn.execute(sql, list(data.values()) + (where_params or []))
            conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, where_params: list = None) -> int:
        """
        软删除：先备份到 _recycle_bin，再执行删除。
        返回删除行数。
        """
        # 备份受影响的行
        rows = self.query(f"SELECT * FROM {table} WHERE {where}", where_params)
        if rows:
            with self._conn() as conn:
                for row in rows:
                    conn.execute(
                        "INSERT INTO _recycle_bin (source_table, source_id, row_json) VALUES (?, ?, ?)",
                        [table, row.get("id"), json.dumps(row, ensure_ascii=False)]
                    )
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE {where}", where_params or []
                )
                conn.commit()
                return cursor.rowcount
        return 0

    def execute_ddl(self, sql: str):
        with self._conn() as conn:
            conn.executescript(sql)

    # ── Schema / 建表 ─────────────────────────────────────────────────────────

    def ensure_table(self, schema_name: str) -> str:
        """
        根据 meta/<schema_name>.json 确保数据表存在，
        并自动补充新增字段（迁移）。
        返回表名。
        """
        schema_path = META_DIR / f"{schema_name}.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema 文件不存在: {schema_path}")

        definition = json.loads(schema_path.read_text(encoding="utf-8"))
        table = f"data_{schema_name}"
        fields = definition.get("fields", [])

        if not self._table_exists(table):
            self._create_table(table, fields)
            logger.info(f"已创建表: {table}")
        else:
            added = self._migrate_table(table, fields)
            if added:
                logger.info(f"表 {table} 新增字段: {added}")

        # 更新系统记录
        existing = self.query_one("SELECT id FROM _meta_schemas WHERE name = ?", [schema_name])
        schema_json = json.dumps(definition, ensure_ascii=False)
        if existing:
            self.update("_meta_schemas",
                {"display_name": definition.get("display_name", schema_name),
                 "schema_json": schema_json},
                "name = ?", [schema_name]
            )
        else:
            self.insert("_meta_schemas", {
                "name": schema_name,
                "display_name": definition.get("display_name", schema_name),
                "description": definition.get("description", ""),
                "schema_json": schema_json,
            })

        return table

    def list_schemas(self) -> list[dict]:
        return self.query("SELECT name, display_name, description, version, updated_at FROM _meta_schemas")

    def _table_exists(self, table: str) -> bool:
        row = self.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]
        )
        return row is not None

    def _create_table(self, table: str, fields: list):
        col_defs = [
            "id           INTEGER PRIMARY KEY AUTOINCREMENT",
            "created_at   TEXT DEFAULT (datetime('now'))",
            "updated_at   TEXT DEFAULT (datetime('now'))",
            "central_id   TEXT DEFAULT NULL",
            "synced       INTEGER DEFAULT 0",
        ]
        for f in fields:
            sql_type = FIELD_TYPE_MAP.get(f["type"], "TEXT")
            not_null = "NOT NULL" if f.get("required") else ""
            col_defs.append(f"    {f['name']:<28} {sql_type} {not_null}".rstrip())

        ddl = f"CREATE TABLE IF NOT EXISTS {table} (\n    " + ",\n    ".join(col_defs) + "\n);"
        self.execute_ddl(ddl)

    def _migrate_table(self, table: str, fields: list) -> list[str]:
        """对比现有列，补充缺失字段（只增不删）"""
        existing_cols = {
            row["name"]
            for row in self.query(f"PRAGMA table_info({table})")
        }
        added = []
        with self._conn() as conn:
            for f in fields:
                if f["name"] not in existing_cols:
                    sql_type = FIELD_TYPE_MAP.get(f["type"], "TEXT")
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {f['name']} {sql_type}")
                    added.append(f["name"])
            if added:
                conn.commit()
        return added

    def _validate(self, table: str, data: dict):
        """根据 _meta_schemas 中的 schema 定义校验数据，校验失败抛出 ValueError。"""
        if not table.startswith("data_"):
            return  # 系统表不校验

        schema_name = table[len("data_"):]
        row = self.query_one(
            "SELECT schema_json FROM _meta_schemas WHERE name = ?", [schema_name]
        )
        if not row:
            return  # schema 未注册，跳过校验

        definition = json.loads(row["schema_json"])
        fields = definition.get("fields", [])
        errors = []

        for f in fields:
            name, ftype, required = f["name"], f["type"], f.get("required", False)
            value = data.get(name)

            # required 检查
            if required and (name not in data or value is None):
                errors.append(f"缺少必填字段: {name}")
                continue

            if value is None:
                continue

            # 类型检查
            if ftype == "number" and not isinstance(value, (int, float)):
                errors.append(f"字段 {name} 应为数字，实际为 {type(value).__name__}: {value!r}")
            elif ftype == "boolean" and value not in (0, 1, True, False):
                errors.append(f"字段 {name} 应为布尔值，实际为: {value!r}")
            elif ftype == "json" and isinstance(value, str):
                try:
                    json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    errors.append(f"字段 {name} 不是合法 JSON: {value!r}")

        if errors:
            raise ValueError(f"数据校验失败 ({table}):\n  " + "\n  ".join(errors))

    def log_sync(self, action: str, schema_name: str, local_id: int,
                 central_id: str, status: str, message: str = ""):
        self.insert("_sync_log", {
            "action": action,
            "schema_name": schema_name,
            "local_id": local_id,
            "central_id": central_id,
            "status": status,
            "message": message,
            "executed_at": _now(),
        })


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── CLI（方便 Claude Code 直接调用测试）──────────────────────────────────────

if __name__ == "__main__":
    import sys, json as _json

    db = DB()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "schemas":
        print(_json.dumps(db.list_schemas(), ensure_ascii=False, indent=2))
    elif cmd == "ensure":
        schema_name = sys.argv[2]
        table = db.ensure_table(schema_name)
        print(f"表已就绪: {table}")
    elif cmd == "query":
        sql = sys.argv[2]
        params = _json.loads(sys.argv[3]) if len(sys.argv) > 3 else []
        rows = db.query(sql, params)
        print(_json.dumps(rows, ensure_ascii=False, indent=2))
    elif cmd == "recycle":
        rows = db.query("SELECT * FROM _recycle_bin ORDER BY deleted_at DESC LIMIT 20")
        print(_json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("用法: python scripts/db.py [schemas|ensure <name>|query <sql>|recycle]")
