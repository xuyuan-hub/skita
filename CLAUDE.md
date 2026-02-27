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
│       └── <skill-name>/       ← 每个 skill 是一个自包含包
│           ├── SKILL.md        ← Skill 使用说明（LLM 读这个来操作）
│           ├── requirements.txt← Skill 自身的依赖声明
│           ├── meta/           ← Skill 自带的 schema 定义
│           ├── scripts/        ← pipeline 代码 + 工具脚本
│           └── tests/          ← 测试脚本和测试数据
├── CLAUDE.md                  ← 你现在读的这里
├── scripts/                   ← 项目级可复用工具
│   ├── db.py                  ← SQLite 操作
│   ├── files.py               ← 文件归档管理
│   └── central.py             ← 中心数据库 HTTP 客户端
├── meta/                      ← Schema 注册目录（skill 运行时自动安装）
└── data/
    ├── skita.db               ← 唯一的本地数据库（所有 skill 共用）
    ├── files/                 ← 长期归档（按 skill/月 分目录）
    ├── workspace/             ← 临时工作区（分析中间产物）
    └── exports/               ← 用户导出文件
```

---

## 数据存储原则

1. **一库统管** — `data/skita.db` 是唯一的本地数据库，所有 skill 的数据表都建在这里（表名 `data_<schema>` 前缀区分）
2. **Schema 双层管理**
   - **源头在 Skill**：每个 skill 在自己的 `meta/` 下定义 schema JSON，随 skill 分发
   - **注册在项目**：skill 运行时自动将 schema 复制到项目 `meta/`，`DB.ensure_table()` 从这里读取建表
3. **本地优先** — 所有数据默认存本地，仅用户主动要求时才同步中心库
4. **文件分层管理** — `data/` 下有三个目录，用途严格区分：

### `data/` 目录规范

```
data/
├── skita.db              ← 数据库（唯一）
├── files/                ← 长期归档（分析产出的重要文件）
│   ├── <skill名>/        ← 按 skill 分子目录
│   │   └── <YYYY-MM>/   ← 按月分子目录
│   │       ├── result.json
│   │       └── report.png
│   └── ...
├── exports/              ← 用户导出（仅用户主动要求导出时使用）
│   └── <描述性文件名>     ← 如 ice_summary_2026-02.csv
└── workspace/            ← 临时工作区（分析过程中的中间产物）
    └── <skill名>/
        └── <项目名_时间戳>/
            └── ...       ← 分析工具的原始输出
```

**三个目录的用途区别**：

| 目录 | 用途 | 写入方式 | 生命周期 |
|------|------|----------|----------|
| `data/files/` | 长期归档，存入数据库引用 | `Files.save(path, category="<skill>")` | 永久保留 |
| `data/exports/` | 用户主动要求的导出文件 | `Files.save_export(content, filename)` | 用户自行管理 |
| `data/workspace/` | 分析过程的临时工作目录 | skill 直接写入，分析完成后可清理 | 临时，可删除 |

**规则**：
- 分析工具（如 `synthego_ice --out`、`CRISPRessoPooled`）的输出 → `data/workspace/<skill>/<项目名>/`
- 分析完成后，从 workspace 中挑选重要文件 → `Files.save()` 归档到 `data/files/`
- **禁止**将分析工具的原始输出直接写入 `data/files/` 或 `data/exports/`
- `data/exports/` 仅用于用户说"导出"、"下载"、"生成报告"时使用

---

## 工作流程

收到任务时：

1. **识别 Skill** → 读 `.claude/skills/<name>/SKILL.md`
2. **执行分析** → 按 SKILL.md 指引运行 pipeline
3. **存储结果** → skill 自动安装 schema、写入 `data/skita.db`、归档文件到 `data/files/`
4. **查询数据** → `DB().query("SELECT ... FROM data_<schema> WHERE ...")`
5. **同步中心库**（用户主动要求时）→ `scripts/central.py`

---

## 依赖管理

项目使用 **uv** 管理依赖，`pyproject.toml` + `uv.lock` 确保可复现。

### 两层依赖架构

| 层级 | 管理方式 | 安装命令 |
|------|----------|----------|
| 项目级 + 兼容 skill | `pyproject.toml` [optional-dependencies] | `uv sync --all-extras` |
| 冲突 skill（如 ice-analysis） | skill 目录下独立 `.venv/` | `pip install` 到 skill venv |

### 项目级依赖

```bash
uv sync                      # 安装核心依赖
uv sync --extra dev           # 安装开发依赖 (pytest)
uv sync --extra crispr-mutation  # 安装 CRISPR skill 依赖
uv sync --all-extras          # 安装全部可选依赖
```

### Skill 级虚拟环境（冲突时使用）

当 skill 依赖与主环境冲突（如 `synthego-ice` 锁定 `pytest==5.2.2`）：

1. 在 skill 目录创建 `.venv/`：`python -m venv .claude/skills/<name>/.venv`
2. 用 skill venv 的 pip 安装依赖
3. SKILL.md 中所有命令使用 `.claude/skills/<name>/.venv/Scripts/` 下的可执行文件
4. `.venv/` 已在 `.gitignore` 中排除

> 原则：主环境由 uv 管理保持干净，冲突 skill 用独立 venv 隔离。

---

## Skill 可移植性设计

**核心理念：每个 Skill 是一个自包含的可移植包。**

当另一个 skita 实例（或另一个 LLM agent 系统）拿到一个 skill 目录时，应该能够快速启动，不需要人工排查依赖。

### Skill 必备文件

```
.claude/skills/<skill-name>/
├── SKILL.md            ← 操作手册（LLM 读这个就知道怎么用）
├── requirements.txt    ← 依赖声明（机器读这个就能安装环境）
├── meta/               ← Schema 定义（数据库表结构随 skill 分发）
├── scripts/            ← 代码实现
└── tests/              ← 测试（验证 skill 可用）
```

### 快速启动流程

新系统接入一个 skill 时只需三步：

```bash
# 1. 安装依赖
pip install -r .claude/skills/<skill-name>/requirements.txt

# 2. 运行测试验证
python -m pytest .claude/skills/<skill-name>/tests/ -v

# 3. 开始使用（LLM 读 SKILL.md 即可操作）
```

### requirements.txt 编写规范

- **声明所有第三方依赖**，包括间接依赖中用户可能需要手动安装的包
- **注释说明非 pip 依赖**（如 Docker 镜像、系统工具）
- **标注已知冲突**（如 `synthego-ice` 锁定 `pytest==5.2.2`，需隔离安装）
- **标注 post-install 操作**（如运行 `patch_ice.py` 修复兼容性）

### 已有 Skill 依赖概览

| Skill | requirements.txt | 隔离安装 | 外部工具 |
|-------|-----------------|----------|----------|
| crispr-mutation | biopython, pyfaidx, pandas, openpyxl | 否（兼容主环境） | Docker (CRISPResso2) |
| ice-analysis | synthego-ice, biopython | **是**（冲突 pytest） | — |
| web-dashboard | streamlit, pandas, openpyxl | 否（兼容主环境） | — |

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

0. **声明依赖** — 在 `<skill>/requirements.txt` 中列出所有第三方依赖
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

## 中心数据库（可选，暂未配置）

需要时在项目根目录创建 `config.json`：
```json
{ "central_url": "https://...", "token": "..." }
```
调用方式见 `scripts/central.py`，仅用户明确要求同步时使用。
