"""
Skita 数据管理网页
启动: streamlit run app.py
"""

import json
import os
import pandas as pd
import streamlit as st
from pathlib import Path

from scripts.db import DB
from scripts.files import Files

ROOT = Path(__file__).parent
FILES_ROOT = ROOT / "data" / "files"
META_DIR = ROOT / "meta"

# ── 页面配置 ─────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Skita", page_icon="🧬", layout="wide")


@st.cache_resource
def get_db():
    return DB()


@st.cache_resource
def get_files():
    return Files()


def load_schema(schema_name: str) -> dict:
    """从 meta/ 加载 schema 定义"""
    path = META_DIR / f"{schema_name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ── 侧边栏导航 ───────────────────────────────────────────────────────────────

db = get_db()
files = get_files()

st.sidebar.title("Skita")
st.sidebar.caption("实验室数据管理")

schemas = db.list_schemas()
schema_map = {s["name"]: s for s in schemas}

pages = ["数据总览"] + [s.get("display_name", s["name"]) for s in schemas] + ["回收站"]
page = st.sidebar.radio("导航", pages, label_visibility="collapsed")


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def get_table_name(schema_name: str) -> str:
    return f"data_{schema_name}"


def render_file_field(value: str):
    """渲染 file_path 类型字段：图片预览或下载链接"""
    if not value:
        return
    abs_p = files.abs_path(value)
    if not abs_p.exists():
        st.caption(f"文件不存在: {value}")
        return
    suffix = abs_p.suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
        st.image(str(abs_p), use_container_width=True)
    elif suffix in (".txt", ".csv", ".tsv", ".log"):
        with st.expander(f"📄 {abs_p.name}", expanded=False):
            try:
                st.code(abs_p.read_text(encoding="utf-8")[:5000])
            except Exception:
                st.warning("无法读取文件内容")
    else:
        st.caption(f"📎 {abs_p.name} ({abs_p.stat().st_size / 1024:.1f} KB)")


def render_edit_form(schema_name: str, schema_def: dict, record: dict):
    """渲染编辑表单"""
    field_defs = schema_def.get("fields", [])
    updated = {}
    for f in field_defs:
        name = f["name"]
        ftype = f["type"]
        current = record.get(name, "")
        if current is None:
            current = ""

        if ftype == "text" or ftype == "file_path" or ftype == "date":
            updated[name] = st.text_input(name, value=str(current), key=f"edit_{record['id']}_{name}")
        elif ftype == "number":
            try:
                val = float(current) if current != "" else 0.0
            except (ValueError, TypeError):
                val = 0.0
            updated[name] = st.number_input(name, value=val, key=f"edit_{record['id']}_{name}")
        elif ftype == "boolean":
            updated[name] = st.checkbox(name, value=bool(current), key=f"edit_{record['id']}_{name}")
        elif ftype == "json":
            updated[name] = st.text_area(name, value=str(current), key=f"edit_{record['id']}_{name}")

    return updated


# ── 页面：数据总览 ────────────────────────────────────────────────────────────

if page == "数据总览":
    st.header("数据总览")

    # 数据库信息
    db_path = ROOT / "data" / "skita.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        st.metric("数据库大小", f"{size_kb:.1f} KB")

    if not schemas:
        st.info("暂无数据表，请先运行分析 pipeline。")
    else:
        cols = st.columns(len(schemas))
        for i, s in enumerate(schemas):
            table = get_table_name(s["name"])
            try:
                count = db.query_one(f"SELECT COUNT(*) as cnt FROM {table}")
                cnt = count["cnt"] if count else 0
            except Exception:
                cnt = "N/A"
            with cols[i]:
                st.metric(s["display_name"], cnt)
                st.caption(s.get("description", ""))
                if s.get("updated_at"):
                    st.caption(f"更新: {s['updated_at']}")

    # 归档文件统计
    st.subheader("归档文件")
    file_list = files.list()
    if file_list:
        st.write(f"共 {len(file_list)} 个文件")
        categories = {}
        for f in file_list:
            cat = f["relative_path"].split("/")[0] if "/" in f["relative_path"] else "other"
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in sorted(categories.items()):
            st.write(f"  - **{cat}**: {count} 个文件")
    else:
        st.info("暂无归档文件。")


# ── 页面：数据表 ──────────────────────────────────────────────────────────────

elif page == "回收站":
    st.header("回收站")

    recycled = db.query("SELECT * FROM _recycle_bin ORDER BY deleted_at DESC")
    if not recycled:
        st.info("回收站为空。")
    else:
        st.write(f"共 {len(recycled)} 条已删除记录")
        for row in recycled:
            with st.expander(f"#{row['id']} | {row['source_table']} (原ID: {row['source_id']}) | 删除于 {row['deleted_at']}"):
                try:
                    data = json.loads(row["row_json"])
                    st.json(data)
                except Exception:
                    st.code(row["row_json"])

                if st.button("恢复此记录", key=f"restore_{row['id']}"):
                    try:
                        data = json.loads(row["row_json"])
                        record_id = data.pop("id", None)
                        data.pop("created_at", None)
                        data.pop("updated_at", None)
                        db.insert(row["source_table"], data)
                        db.query(f"DELETE FROM _recycle_bin WHERE id = ?", [row["id"]])
                        st.success("已恢复！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"恢复失败: {e}")

else:
    # 通用数据表页面
    schema_name = None
    for s in schemas:
        if s.get("display_name", s["name"]) == page:
            schema_name = s["name"]
            break

    if not schema_name:
        st.error("未找到对应的数据表。")
        st.stop()

    schema_def = load_schema(schema_name)
    table = get_table_name(schema_name)
    field_defs = schema_def.get("fields", [])
    file_fields = [f["name"] for f in field_defs if f["type"] == "file_path"]

    st.header(schema_def.get("display_name", schema_name))
    st.caption(schema_def.get("description", ""))

    # 搜索过滤
    search = st.text_input("搜索", placeholder="输入关键词过滤...", label_visibility="collapsed")

    # 加载数据
    try:
        rows = db.query(f"SELECT * FROM {table} ORDER BY id DESC")
    except Exception as e:
        st.error(f"查询失败: {e}")
        st.stop()

    if not rows:
        st.info("暂无数据。")
        st.stop()

    df = pd.DataFrame(rows)

    # 搜索过滤
    if search:
        mask = df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        df = df[mask]

    st.write(f"共 {len(df)} 条记录")

    # 导出按钮
    col_export, col_spacer = st.columns([1, 5])
    with col_export:
        csv_data = df.to_csv(index=False)
        st.download_button(
            "导出 CSV",
            data=csv_data,
            file_name=f"{schema_name}.csv",
            mime="text/csv",
        )

    # 数据表展示
    display_cols = [c for c in df.columns if c not in ("central_id", "synced")]
    event = st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # 选中行详情
    selected_rows = event.selection.rows if event.selection else []

    if selected_rows:
        idx = selected_rows[0]
        record = df.iloc[idx].to_dict()
        record_id = record.get("id")

        st.divider()
        detail_tab, edit_tab = st.tabs(["详情", "编辑"])

        with detail_tab:
            # 分两列显示：左侧字段，右侧文件预览
            col_info, col_files = st.columns([1, 1])

            with col_info:
                for f in field_defs:
                    name = f["name"]
                    val = record.get(name, "")
                    if f["type"] != "file_path":
                        if f["type"] == "json" and val:
                            st.write(f"**{name}**")
                            try:
                                st.json(json.loads(val) if isinstance(val, str) else val)
                            except Exception:
                                st.code(str(val))
                        else:
                            st.write(f"**{name}**: {val}")

                st.caption(f"创建: {record.get('created_at', '')} | 更新: {record.get('updated_at', '')}")

            with col_files:
                if file_fields:
                    for fname in file_fields:
                        val = record.get(fname, "")
                        if val:
                            st.write(f"**{fname}**")
                            render_file_field(val)

        with edit_tab:
            with st.form(key=f"edit_form_{record_id}"):
                updated = render_edit_form(schema_name, schema_def, record)
                col_save, col_delete = st.columns([1, 1])

                with col_save:
                    if st.form_submit_button("保存修改", type="primary"):
                        changes = {k: v for k, v in updated.items() if v != record.get(k)}
                        if changes:
                            db.update(table, changes, "id = ?", [record_id])
                            st.success("已保存！")
                            st.rerun()
                        else:
                            st.info("无修改。")

                with col_delete:
                    if st.form_submit_button("删除记录", type="secondary"):
                        db.delete(table, "id = ?", [record_id])
                        st.success("已移入回收站。")
                        st.rerun()
