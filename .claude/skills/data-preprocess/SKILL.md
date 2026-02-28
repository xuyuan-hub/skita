---
name: data-preprocess
description: 解析特定格式的数据文件（如生工引物订购表、仪器导出文件等）。当需要读取或处理实验室常用的特定格式文件时优先使用此skill。
---

# Data Preprocess

解析实验室常用的特定格式数据文件，提取结构化信息并存入数据库。

## 触发时机

遇到以下文件时**必须优先使用此skill**，而非直接用 pandas/openpyxl 读取：
- 生工（Sangon）引物订购表 Excel
- 其他供应商特定格式的订购表/报价单
- 仪器导出的特殊格式文件

## 前置条件

- Python 3.10+ with dependencies: `pip install openpyxl pandas`
- 完整依赖见 `requirements.txt`

## 目录结构

```
data-preprocess/
├── SKILL.md            ← 本文件
├── requirements.txt    ← 依赖声明
├── meta/
│   └── sangon_primer_order.json  ← Schema 定义
├── scripts/
│   └── extract_sangon_order_xlsx.py  ← 生工订购表提取脚本
└── tests/
    ├── test_extract_sangon.py
    └── data/
        └── 引物订购表-26-01-12.xlsx
```

## 功能一览

### 生工引物订购表解析

**脚本**: `scripts/extract_sangon_order_xlsx.py`

```bash
# 仅提取并打印摘要
python scripts/extract_sangon_order_xlsx.py order.xlsx

# 提取并存入数据库（推荐）
python scripts/extract_sangon_order_xlsx.py order.xlsx --save-db

# 提取并保存为 JSON
python scripts/extract_sangon_order_xlsx.py order.xlsx --json output.json

# 同时存库和导出 JSON
python scripts/extract_sangon_order_xlsx.py order.xlsx --save-db --json output.json
```

**Python API**:

```python
from extract_sangon_order_xlsx import PrimerOrderExtractor

extractor = PrimerOrderExtractor("order.xlsx")
data = extractor.extract_all()           # 提取数据
row_id = extractor.save_to_db(data)      # 存入数据库
extractor.print_summary(data)            # 打印摘要
```

## 数据存储

### Schema: `sangon_primer_order`

| 字段 | 类型 | 说明 |
|------|------|------|
| source_file | file_path | 源文件归档路径 |
| customer_name | text | 订购人姓名 |
| customer_phone | text | 订购人手机 |
| customer_email | text | 订购人邮箱 |
| company_name | text | 订购人单位 |
| order_date | date | 订购日期 |
| payment_method | text | 付款方式 |
| primer_count | number | 引物数量 |
| primer_data | json | 引物详细数据（数组） |
| order_info | json | 完整订单信息 |
| output_file | file_path | JSON 输出文件路径 |

### 存储流程

1. 自动安装 schema 到项目 `meta/`
2. `DB.ensure_table("sangon_primer_order")` 建表
3. 源 Excel 文件归档到 `data/files/data-preprocess/<YYYY-MM>/`
4. 结构化数据写入 `data_sangon_primer_order` 表

### 查询示例

```python
from scripts.db import DB
db = DB()

# 查询所有引物订购记录
db.query("SELECT * FROM data_sangon_primer_order ORDER BY created_at DESC")

# 按客户名查询
db.query("SELECT * FROM data_sangon_primer_order WHERE customer_name = ?", ["张三"])
```

## 注意事项

1. **脚本位置**：所有解析脚本在本 skill 的 `scripts/` 目录下
2. **源文件归档**：`--save-db` 会自动将源 Excel 归档到 `data/files/data-preprocess/`
3. **引物数据存为 JSON 字段**：单条记录包含该订购表所有引物，通过 `json.loads(primer_data)` 解析
