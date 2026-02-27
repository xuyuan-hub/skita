# SKITA — 生物实验室数据管理框架

SKITA 是一个 **LLM 驱动**的生物实验室数据管理系统。没有传统 UI，没有后端服务——Claude Code 就是操作层。用户通过自然语言对话完成数据录入、实验分析、查询导出等全部操作。

## 核心特点

- **对话即操作** — 通过 Claude Code 驱动，自然语言完成所有实验数据管理
- **Skill 插件化** — 每类实验封装为独立 Skill，自包含、可移植、即插即用
- **本地优先** — 数据存储在本地 SQLite，无需外部服务即可运行
- **Schema 驱动** — JSON 定义数据结构，自动建表、校验、迁移

## 项目结构

```
skita/
├── .claude/skills/          # Skill 包（每个对应一类实验）
│   ├── crispr-mutation/     # CRISPR/Cas9 突变分析 (NGS)
│   ├── ice-analysis/        # CRISPR 编辑效率分析 (Sanger)
│   └── web-dashboard/       # Streamlit 数据可视化
├── scripts/                 # 项目级工具
│   ├── db.py                # SQLite 数据库操作
│   ├── files.py             # 文件归档管理
│   └── central.py           # 中心数据库同步（可选）
├── meta/                    # Schema 注册目录
├── data/                    # 数据存储
│   ├── skita.db             # SQLite 数据库
│   ├── files/               # 长期归档
│   ├── workspace/           # 分析临时工作区
│   └── exports/             # 用户导出文件
├── CLAUDE.md                # LLM 操作指引
└── pyproject.toml           # 项目依赖配置
```

## 已有 Skills

| Skill | 数据类型 | 用途 |
|-------|----------|------|
| **crispr-mutation** | NGS (FASTQ) | CRISPR/Cas9 深度测序突变分析，基于 CRISPResso2 |
| **ice-analysis** | Sanger (.ab1) | CRISPR 编辑效率快速评估，基于 Synthego ICE |
| **web-dashboard** | — | Streamlit 网页界面，数据浏览与管理 |

## 安装

### 前置条件

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI

### 安装核心依赖

```bash
# 克隆项目
git clone <repo-url> skita
cd skita

# 安装核心依赖（pandas, openpyxl）
uv sync

# 安装开发依赖（pytest）
uv sync --extra dev
```

### 安装 Skill 依赖

按需安装你要使用的 Skill：

```bash
# CRISPR 突变分析（还需要 Docker + CRISPResso2 镜像）
uv sync --extra crispr-mutation

# Web 数据面板
uv sync --extra web-dashboard

# PDF 报告生成
uv sync --extra pdf

# 一次安装全部兼容依赖
uv sync --all-extras
```

**ICE 分析**需要隔离安装（因 `synthego-ice` 与主环境 pytest 版本冲突）：

```bash
# 创建 skill 级虚拟环境
python -m venv .claude/skills/ice-analysis/.venv

# 安装依赖
.claude/skills/ice-analysis/.venv/Scripts/pip install -r .claude/skills/ice-analysis/requirements.txt

# 修复 Biopython 兼容性
.claude/skills/ice-analysis/.venv/Scripts/python .claude/skills/ice-analysis/scripts/patch_ice.py
```

## 使用方式

启动 Claude Code，用自然语言对话即可：

```bash
claude
```

示例对话：

```
> 分析这批 CRISPR 编辑的 Sanger 测序结果
> 查看最近的实验数据
> 把上周的 ICE 分析结果导出为 Excel
> 启动数据面板
```

Claude Code 会自动识别对应 Skill，读取 SKILL.md 获取操作指引，执行分析并存储结果。

## 运行测试

```bash
# 项目级工具测试
uv run pytest scripts/tests/ -v

# ICE 分析测试（使用 skill 的隔离环境）
.claude/skills/ice-analysis/.venv/Scripts/pytest .claude/skills/ice-analysis/tests/ -v
```

## 添加新 Skill

每个 Skill 是一个自包含的可移植包，放入 `.claude/skills/` 即可被系统识别：

```
.claude/skills/<skill-name>/
├── SKILL.md             # 操作手册（LLM 读这个来操作）
├── requirements.txt     # 依赖声明（安装环境用）
├── meta/                # Schema 定义（数据表结构）
├── scripts/             # 代码实现
└── tests/               # 测试验证
```

接入新 skill 只需三步：

```bash
pip install -r .claude/skills/<skill-name>/requirements.txt
python -m pytest .claude/skills/<skill-name>/tests/ -v
# 然后用自然语言告诉 Claude Code 即可
```

## License

Private project.
