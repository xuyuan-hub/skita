"""
save_results.py
将 CRISPResso pipeline 运行结果存入本地 SQLite 和文件系统。

用法：
    from save_results import save_pipeline_results
    run_id = save_pipeline_results(config, work_dir, mutation_tsv, log)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 路径常量
SKILL_DIR = Path(__file__).resolve().parents[1]      # scripts/ -> crispr-mutation/
SKILL_META_DIR = SKILL_DIR / "meta"                   # skill 自带的 schema 定义
PROJECT_ROOT = Path(__file__).resolve().parents[4]    # scripts/ -> crispr-mutation/ -> skills/ -> .claude/ -> skita/
PROJECT_META_DIR = PROJECT_ROOT / "meta"              # 项目的 meta/ 目录

sys.path.insert(0, str(PROJECT_ROOT))

# 当前 scripts 目录（用于导入 mutation_define_NGS）
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.db import DB
from scripts.files import Files

import shutil
import pandas as pd


def _install_schemas():
    """将 skill 自带的 schema 文件同步到项目 meta/ 目录，ensure_table 才能找到。"""
    PROJECT_META_DIR.mkdir(parents=True, exist_ok=True)
    for schema_file in SKILL_META_DIR.glob("*.json"):
        target = PROJECT_META_DIR / schema_file.name
        if not target.exists() or target.read_bytes() != schema_file.read_bytes():
            shutil.copy2(schema_file, target)


def save_pipeline_results(
    project_name: str,
    csv_path: Path,
    r1_path: Path,
    r2_path: Path,
    work_dir: Path,
    log_callback=None,
) -> int | None:
    """
    将 pipeline 结果存入本地数据库和文件系统。

    Args:
        project_name: 项目名
        csv_path: 输入 CSV 路径
        r1_path: R1 FASTQ 路径
        r2_path: R2 FASTQ 路径
        work_dir: pipeline 输出的工作目录 (output_dir/project_name/)
        log_callback: 日志回调函数

    Returns:
        run_id (int) 或 None（失败时）
    """
    def _log(msg):
        if log_callback:
            log_callback(msg)

    try:
        db = DB()
        files = Files()

        # 将 skill 自带的 schema 同步到项目 meta/，然后建表
        _install_schemas()
        db.ensure_table("crispr_mutation_run")
        db.ensure_table("crispr_mutation_sample")

        # --- 读取输入 CSV 获取 locus/target 信息 ---
        # 支持多种 CSV 格式：列名可能是 GeoID/pid, Locus/locus, Target/target
        input_df = pd.read_csv(csv_path)
        col_map = {}
        for col in input_df.columns:
            low = col.lower()
            if low in ("geoid", "pid", "geo_id", "sample_id"):
                col_map[col] = "GeoID"
            elif low in ("locus",):
                col_map[col] = "Locus"
            elif low in ("target",):
                col_map[col] = "Target"
        input_df = input_df.rename(columns=col_map)
        sample_info = {row["GeoID"]: row for _, row in input_df.iterrows()}
        total_samples = len(input_df)

        # --- 收集结果目录 ---
        results_txt_dir = work_dir / f"{project_name}_Results_Txt"
        results_png_dir = work_dir / f"{project_name}_Results_Png"

        # 成功样本 = Results_Txt 中有结果的样本
        success_ids = set()
        if results_txt_dir.exists():
            success_ids = {f.stem for f in results_txt_dir.glob("*.txt")}
        failed_ids = sorted(set(sample_info.keys()) - success_ids)

        # --- 生成/读取 mutation.tsv ---
        mutation_tsv = None
        # 查找已有的 mutation.tsv
        for tsv in work_dir.glob("*_mutation.tsv"):
            mutation_tsv = tsv
            break

        # 如果不存在且 Results_Txt 目录有文件，自动生成
        if mutation_tsv is None and results_txt_dir.exists() and success_ids:
            _log("    正在生成突变分析结果...")
            try:
                from mutation_define_NGS import process_all_txt_files
                mutation_tsv_path = process_all_txt_files(str(results_txt_dir))
                mutation_tsv = Path(mutation_tsv_path)
                _log(f"    mutation.tsv 已生成: {mutation_tsv}")
            except Exception as e:
                _log(f"    [WARNING] 突变分析失败: {e}")

        mutations = {}  # sample_id -> interpretation
        if mutation_tsv and mutation_tsv.exists():
            with open(mutation_tsv, encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t", 1)
                    if len(parts) == 2:
                        mutations[parts[0]] = parts[1]

        # --- 保存文件 ---
        # 保存 CSV
        csv_result = files.save(str(csv_path), "crispr-mutation", f"{project_name}.csv")
        csv_rel = csv_result["relative_path"]
        _log(f"    CSV 已存储: {csv_rel}")

        # 保存 mutation.tsv
        mutation_rel = None
        if mutation_tsv and mutation_tsv.exists():
            mut_result = files.save(str(mutation_tsv), "crispr-mutation", f"{project_name}_mutation.tsv")
            mutation_rel = mut_result["relative_path"]
            _log(f"    mutation.tsv 已存储: {mutation_rel}")

        # --- 插入 run 记录 ---
        run_id = db.insert("data_crispr_mutation_run", {
            "project_name": project_name,
            "csv_file": csv_rel,
            "r1_file": str(r1_path),
            "r2_file": str(r2_path),
            "total_samples": total_samples,
            "success_samples": len(success_ids),
            "failed_samples": json.dumps(failed_ids, ensure_ascii=False),
            "mutation_file": mutation_rel,
            "output_dir": str(work_dir),
            "run_date": datetime.now().strftime("%Y-%m-%d"),
        })
        _log(f"    运行记录已保存 (run_id={run_id})")

        # --- 插入 sample 记录 + 保存 TXT/PNG 文件 ---
        saved_count = 0
        for sample_id in sorted(success_ids):
            info = sample_info.get(sample_id, {})

            # 保存 TXT 文件
            txt_rel = None
            txt_file = results_txt_dir / f"{sample_id}.txt"
            if txt_file.exists():
                txt_result = files.save(str(txt_file), "crispr-mutation", f"{sample_id}.txt")
                txt_rel = txt_result["relative_path"]

            # 保存 PNG 文件
            png_rel = None
            if results_png_dir.exists():
                png_file = results_png_dir / f"{sample_id}.png"
                if png_file.exists():
                    png_result = files.save(str(png_file), "crispr-mutation", f"{sample_id}.png")
                    png_rel = png_result["relative_path"]

            # 获取突变解读
            interpretation = mutations.get(sample_id, "")

            db.insert("data_crispr_mutation_sample", {
                "run_id": run_id,
                "sample_id": sample_id,
                "locus": info.get("Locus", ""),
                "target": info.get("Target", ""),
                "interpretation": interpretation,
                "txt_file": txt_rel,
                "png_file": png_rel,
            })
            saved_count += 1

        _log(f"    样本记录已保存: {saved_count} 条")
        return run_id

    except Exception as e:
        _log(f"[ERROR] 保存结果失败: {e}")
        import traceback
        _log(traceback.format_exc())
        return None
