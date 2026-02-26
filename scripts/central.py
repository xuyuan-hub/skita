"""
scripts/central.py
中心数据库 HTTP 客户端（RESTful API）。
不需要任何常驻进程，按需调用即可。

假设中心数据库 API 格式：
    GET  /health                         → {"status": "ok"}
    POST /records                        → 上传，body: {schema, lab_id, data, idempotency_key}
    GET  /records/<central_id>           → 下载单条
    GET  /records?schema=&limit=&...     → 查询
    POST /records/<central_id>/files     → 上传文件（multipart）
"""

import json
import hashlib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.json"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _headers(token: str) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _http(method: str, url: str, body: dict = None, token: str = "",
          timeout: int = 30) -> dict:
    """极简 HTTP 客户端，仅用标准库，无需 requests/httpx"""
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "status": resp.status,
                    "data": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        return {"ok": False, "status": e.code, "error": body_text}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}


class Central:
    def __init__(self):
        cfg = _load_config()
        self.base_url = cfg.get("central_url", "").rstrip("/")
        self.token = cfg.get("token", "")
        self.lab_id = cfg.get("lab_id", "")
        self.timeout = cfg.get("timeout_seconds", 30)

    def _check_config(self):
        if not self.base_url:
            raise ValueError(
                "中心数据库未配置，请编辑 config.json 填写 central_url 和 token"
            )

    # ── 连接测试 ──────────────────────────────────────────────────────────────

    def connect(self) -> dict:
        self._check_config()
        result = _http("GET", f"{self.base_url}/health", token=self.token, timeout=10)
        return {
            "connected": result["ok"],
            "endpoint": self.base_url,
            "detail": result.get("data") or result.get("error"),
        }

    # ── 上传 ──────────────────────────────────────────────────────────────────

    def upload(self, schema_name: str, record: dict, local_id: int = None) -> dict:
        """
        上传单条记录。
        idempotency_key 由 schema + local_id + created_at 生成，防止重复上传。
        """
        self._check_config()

        idem_key = _idem_key(schema_name, local_id, record.get("created_at", ""))
        payload = {
            "schema": schema_name,
            "lab_id": self.lab_id,
            "idempotency_key": idem_key,
            "data": _strip_local_fields(record),
        }
        result = _http("POST", f"{self.base_url}/records", body=payload, token=self.token)
        if result["ok"]:
            return {"success": True, "central_id": result["data"].get("id"),
                    "idempotency_key": idem_key}
        return {"success": False, "error": result.get("error"), "status": result["status"]}

    def upload_batch(self, schema_name: str, records: list[dict]) -> dict:
        """批量上传，逐条上传并汇总结果"""
        ok, failed = [], []
        for rec in records:
            r = self.upload(schema_name, rec, local_id=rec.get("id"))
            if r["success"]:
                ok.append({"local_id": rec.get("id"), "central_id": r["central_id"]})
            else:
                failed.append({"local_id": rec.get("id"), "error": r["error"]})
        return {"success": len(failed) == 0, "uploaded": len(ok),
                "failed": len(failed), "details": {"ok": ok, "failed": failed}}

    # ── 下载 ──────────────────────────────────────────────────────────────────

    def download(self, central_id: str) -> dict:
        self._check_config()
        result = _http("GET", f"{self.base_url}/records/{central_id}", token=self.token)
        if result["ok"]:
            return {"success": True, "schema": result["data"].get("schema"),
                    "data": result["data"].get("data", {}), "central_id": central_id}
        return {"success": False, "error": result.get("error")}

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def query(self, schema_name: str, filters: dict = None, limit: int = 20) -> dict:
        self._check_config()
        params = {"schema": schema_name, "lab_id": self.lab_id, "limit": limit}
        if filters:
            params.update(filters)
        url = f"{self.base_url}/records?" + urllib.parse.urlencode(params)
        result = _http("GET", url, token=self.token)
        if result["ok"]:
            return {"success": True, "records": result["data"].get("records", []),
                    "total": result["data"].get("total", 0)}
        return {"success": False, "error": result.get("error")}


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _idem_key(schema: str, local_id, created_at: str) -> str:
    raw = f"{schema}:{local_id}:{created_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _strip_local_fields(record: dict) -> dict:
    """去掉本地专属字段，避免污染中心数据库"""
    skip = {"id", "synced", "central_id"}
    return {k: v for k, v in record.items() if k not in skip}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    c = Central()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "connect"

    if cmd == "connect":
        print(json.dumps(c.connect(), ensure_ascii=False, indent=2))
    elif cmd == "query":
        schema = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        print(json.dumps(c.query(schema, limit=limit), ensure_ascii=False, indent=2))
    elif cmd == "download":
        print(json.dumps(c.download(sys.argv[2]), ensure_ascii=False, indent=2))
    else:
        print("用法: python scripts/central.py [connect|query <schema>|download <id>]")
