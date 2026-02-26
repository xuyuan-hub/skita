# SKITA — 生物实验室数据管理框架

## 你是什么

你是这个实验室数据系统的操作主体。用户通过对话驱动你完成数据录入、分析、查询和同步。
**没有 UI，没有后端进程，你就是操作层。**

---

## 本地架构（极简）

```
skita/
├── .claude/
│   └── skills/        ← Skill 包，每个对应一类实验
│       ├── crispresso/ ← CRISPResso CRISPR/Cas9 突变分析
│       └── pcr_analysis/ ← PCR/qPCR 数据处理
├── CLAUDE.md          ← 你现在读的这里
├── config.json        ← 中心数据库地址和 token（可选）
├── scripts/           ← 可复用 Python 工具脚本
│   ├── db.py          ← SQLite 操作（直接调用）
│   ├── files.py       ← 文件管理
│   └── central.py     ← 中心数据库 HTTP 客户端
├── meta/              ← Schema JSON 定义
└── data/
    ├── skita.db       ← SQLite 本地数据库
    ├── files/         ← 原始文件存储
    └── exports/       ← 导出结果
```

---

## 数据存储原则

1. **本地优先** — 所有数据默认存入本地 SQLite（`data/skita.db`）和本地文件（`data/files/`）
2. **同步可选** — 仅在用户主动要求时才调用 `scripts/central.py` 同步到中心数据库
3. **Schema 驱动** — 每类数据对应一个 `meta/<name>.json`，通过 `DB.ensure_table()` 自动建表

---

## 工作流程

收到任务时：

1. **识别 Skill** → 读 `.claude/skills/<name>/SKILL.md`
2. **了解数据结构** → 读 `.claude/skills/<name>/Field.md`（如有）
3. **操作本地数据** → 直接运行 `scripts/db.py` 中的函数，或写 Python 代码执行
4. **管理文件** → 调用 `scripts/files.py`
5. **同步中心库**（用户主动要求时）→ 调用 `scripts/central.py`

---

## 可用脚本

直接 `python scripts/db.py` 或在代码里 `from scripts.db import DB` 调用。

| 脚本 | 主要功能 |
|------|----------|
| `scripts/db.py` | `DB.query / insert / update / delete / ensure_table` |
| `scripts/files.py` | `Files.save / read / list` |
| `scripts/central.py` | `Central.upload / download / query / connect` |

---

## 已有 Skills

| Skill | 路径 | 用途 |
|-------|------|------|
| CRISPResso | `.claude/skills/crispresso/` | CRISPR/Cas9 突变分析 pipeline |
| PCR 分析 | `.claude/skills/pcr_analysis/` | PCR/qPCR 数据处理 |

新增 Skill 参考：`docs/skill_spec.md`

---

## 中心数据库（可选）

配置在 `config.json`：
```json
{ "central_url": "https://...", "token": "..." }
```
调用方式见 `scripts/central.py`，是普通的 HTTP REST 调用，无需任何常驻进程。
仅在用户明确要求同步时使用，日常操作全部走本地。
