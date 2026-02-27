# SKITA — 生物实验室数据管理框架

## 你是什么

你是这个实验室数据系统的操作主体。用户通过对话驱动你完成数据录入、分析、查询和同步。
**没有 UI，没有后端进程，你就是操作层。**

---

## 本地架构

```
skita/
├── .claude/
│   └── skills/                ← Skill 包，每个对应一类实验
│       └── crispr-mutation/    ← CRISPR/Cas9 突变分析（目前唯一 skill）
│           ├── SKILL.md       ← Skill 使用说明（LLM 读这个来操作）
│           ├── meta/          ← Skill 自带的 schema 定义
│           ├── scripts/       ← pipeline 代码 + 工具脚本
│           ├── genomes/       ← 参考基因组（大文件，不入 Git）
│           └── tests/         ← 测试脚本和测试数据
├── CLAUDE.md                  ← 你现在读的这里
├── scripts/                   ← 项目级可复用工具
│   ├── db.py                  ← SQLite 操作
│   ├── files.py               ← 文件归档管理
│   └── central.py             ← 中心数据库 HTTP 客户端
├── meta/                      ← Schema 注册目录（skill 运行时自动安装）
└── data/
    ├── skita.db               ← 唯一的本地数据库（所有 skill 共用）
    ├── files/                 ← 文件归档存储（按 skill 分子目录）
    └── exports/               ← 导出结果
```

---

## 数据存储原则

1. **一库统管** — `data/skita.db` 是唯一的本地数据库，所有 skill 的数据表都建在这里（表名 `data_<schema>` 前缀区分）
2. **Schema 双层管理**
   - **源头在 Skill**：每个 skill 在自己的 `meta/` 下定义 schema JSON，随 skill 分发
   - **注册在项目**：skill 运行时自动将 schema 复制到项目 `meta/`，`DB.ensure_table()` 从这里读取建表
3. **本地优先** — 所有数据默认存本地，仅用户主动要求时才同步中心库
4. **文件按类归档** — `Files.save(source, category="<skill名>")` → `data/files/<skill名>/<YYYY-MM>/`

---

## 工作流程

收到任务时：

1. **识别 Skill** → 读 `.claude/skills/<name>/SKILL.md`
2. **执行分析** → 按 SKILL.md 指引运行 pipeline
3. **存储结果** → skill 自动安装 schema、写入 `data/skita.db`、归档文件到 `data/files/`
4. **查询数据** → `DB().query("SELECT ... FROM data_<schema> WHERE ...")`
5. **同步中心库**（用户主动要求时）→ `scripts/central.py`

---

## 文档更新原则

在执行过程中遇到问题时，**必须及时更新相关文档**以避免重复踩坑：

1. **遇到错误必记录** — 执行中遇到的报错、坑点、依赖问题等，必须记录到对应的 SKILL.md
2. **记录内容包括**：
   - 错误现象（错误信息、错误类型）
   - 原因分析
   - 解决方案或正确用法
3. **更新位置**：
   - Skill 相关问题 → `.claude/skills/<name>/SKILL.md`
   - 项目级问题 → `CLAUDE.md`
   - 脚本使用问题 → 对应脚本的注释或文档字符串

---

## 项目级工具脚本

| 脚本 | 用法 | 主要接口 |
|------|------|----------|
| `scripts/db.py` | `from scripts.db import DB` | `query / insert / update / delete / ensure_table / list_schemas` |
| `scripts/files.py` | `from scripts.files import Files` | `save / read_text / list / abs_path / save_export` |
| `scripts/central.py` | `from scripts.central import Central` | `upload / download / query / connect` |

---

## Skill 数据存储规范

每个 skill 如需持久化数据，遵循以下约定：

1. **定义 Schema** — 在 `<skill>/meta/<name>.json` 中声明：
   ```json
   {
     "display_name": "显示名",
     "description": "说明",
     "version": 1,
     "fields": [
       {"name": "字段名", "type": "text|number|date|boolean|file_path|json", "required": true}
     ]
   }
   ```
2. **自动安装** — 存储脚本在写入前将 schema 复制到项目 `meta/`，再调用 `DB.ensure_table()`
3. **表名 = 文件名** — `meta/crispr_mutation_run.json` → 表 `data_crispr_mutation_run`
4. **文件归档** — `Files.save(path, category="<skill名>")`

---

## 已有 Skills

| Skill | 路径 | 数据表 | 用途 |
|-------|------|--------|------|
| CRISPR Mutation | `.claude/skills/crispr-mutation/` | `data_crispr_mutation_run`、`data_crispr_mutation_sample` | CRISPR/Cas9 突变分析 pipeline (NGS) |
| ICE Analysis | `.claude/skills/ice-analysis/` | `data_ice_run`、`data_ice_result` | CRISPR 编辑分析 (Sanger 测序) |
| Web Dashboard | `.claude/skills/web-dashboard/` | - | Streamlit 网页界面，数据可视化管理 |

---

## 中心数据库（可选，暂未配置）

需要时在项目根目录创建 `config.json`：
```json
{ "central_url": "https://...", "token": "..." }
```
调用方式见 `scripts/central.py`，仅用户明确要求同步时使用。
