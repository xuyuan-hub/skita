---
name: web-dashboard
description: 启动 Streamlit 网页来展示和管理 skita 数据库。当用户想要查看数据、管理记录、启动网页界面、可视化数据、浏览实验结果时使用此 skill。支持数据总览、运行记录/样本结果的浏览/编辑/删除/导出、回收站恢复功能。
---

# Web Dashboard

启动一个 Streamlit 网页界面来展示和管理 skita 本地数据库。

## 何时使用

- 用户想查看数据库中的数据
- 用户想通过网页界面管理记录（编辑、删除、导出）
- 用户说"打开网页"、"启动界面"、"查看数据"、"数据可视化"
- 用户想浏览 CRISPR 分析结果

## 启动方式

在项目根目录执行（**必须设置 PYTHONPATH** 以确保 `scripts` 模块可被导入）：

```bash
PYTHONPATH="$PWD" uv run streamlit run .claude/skills/web-dashboard/scripts/dashboard.py
```

> **注意**: 如果不设置 PYTHONPATH，Streamlit 运行时可能无法找到 `scripts.db` 和 `scripts.files` 模块，导致 `ModuleNotFoundError: No module named 'scripts'` 错误。

启动后会自动打开浏览器，默认地址 `http://localhost:8501`。

## 功能说明

### 数据总览

- 显示已注册的 schema 列表
- 每个数据表的记录数统计
- 数据库文件大小
- 归档文件统计

### 数据表页面

对于每个已注册的 schema（如运行记录、样本结果）：

- **浏览**：表格展示所有数据，支持排序
- **搜索**：关键词过滤
- **详情**：点击行查看完整信息，图片/文本文件自动预览
- **编辑**：修改记录字段
- **删除**：软删除到回收站
- **导出**：一键导出 CSV

### 回收站

- 查看所有已删除记录
- 支持恢复到原数据表

## 技术细节

- 复用 `scripts/db.py` 和 `scripts/files.py`
- 根据 `meta/` 下的 schema 定义动态生成页面
- 新增 skill 后无需修改代码，自动识别新数据表
