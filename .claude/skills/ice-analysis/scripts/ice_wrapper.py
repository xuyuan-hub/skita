"""
ICE 分析包装器
封装 Synthego ICE 工具，提供便捷的分析接口和数据库存储
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# 项目根目录
SKILL_DIR = Path(__file__).parent
ROOT = SKILL_DIR.parent.parent.parent


@dataclass
class ICEResult:
    """ICE 分析结果"""

    sample_id: str
    target_sequence: str
    editing_efficiency: float
    deletion_pct: float = 0.0
    insertion_pct: float = 0.0
    wt_pct: float = 0.0
    indel_summary: dict = field(default_factory=dict)
    report_dir: Optional[str] = None


class ICEAnalyzer:
    """ICE 分析器包装类"""

    def __init__(
        self,
        control: Path,
        edited: Path,
        target: str,
        output_dir: Optional[Path] = None,
        donor: Optional[str] = None,
    ):
        """
        初始化 ICE 分析器

        Args:
            control: 对照样本 .ab1 文件
            edited: 编辑样本 .ab1 文件
            target: gRNA 目标序列 (17-23 bp)
            output_dir: 输出目录
            donor: HDR 供体序列（可选）
        """
        self.control = Path(control)
        self.edited = Path(edited)
        self.target = target
        self.output_dir = Path(output_dir) if output_dir else self.control.parent / "ice_results"
        self.donor = donor

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 样本 ID 从文件名提取
        self.sample_id = self.edited.stem.replace("_edited", "").replace("-edited", "")

    def _check_ice_installed(self) -> bool:
        """检查 ICE 是否已安装"""
        try:
            result = subprocess.run(
                ["synthego_ice", "--version"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def run(self) -> ICEResult:
        """
        执行 ICE 分析

        Returns:
            ICEResult 对象
        """
        # 检查 ICE 是否安装
        if not self._check_ice_installed():
            raise RuntimeError(
                "ICE 未安装。请运行: pip install synthego-ice\n"
                "或使用 Docker: docker pull synthego/ice:latest"
            )

        # 构建命令
        cmd = [
            "synthego_ice",
            "--control", str(self.control),
            "--edited", str(self.edited),
            "--target", self.target,
            "--out", str(self.output_dir / self.sample_id),
        ]

        if self.donor:
            cmd.extend(["--donor", self.donor])

        # 执行分析
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ICE 分析失败: {result.stderr}")

        # 解析结果
        return self._parse_results()

    def _parse_results(self) -> ICEResult:
        """解析 ICE 输出结果"""
        result_dir = self.output_dir / self.sample_id

        # 读取 indel 分布文件
        indel_file = result_dir / f"{self.sample_id}_indel.json"
        indel_data = {}
        if indel_file.exists():
            with open(indel_file) as f:
                indel_data = json.load(f)

        # 计算编辑效率
        editing_efficiency = 0.0
        deletion_pct = 0.0
        insertion_pct = 0.0
        wt_pct = 100.0

        if indel_data:
            # 从 indel 数据中提取统计
            for key, value in indel_data.items():
                if key == "0":
                    wt_pct = value * 100
                elif key.startswith("-"):
                    deletion_pct += value * 100
                elif key.startswith("+"):
                    insertion_pct += value * 100

            editing_efficiency = 100.0 - wt_pct

        return ICEResult(
            sample_id=self.sample_id,
            target_sequence=self.target,
            editing_efficiency=round(editing_efficiency, 1),
            deletion_pct=round(deletion_pct, 1),
            insertion_pct=round(insertion_pct, 1),
            wt_pct=round(wt_pct, 1),
            indel_summary=indel_data,
            report_dir=str(result_dir),
        )

    def to_dict(self, result: ICEResult) -> dict:
        """将结果转换为字典"""
        return {
            "sample_id": result.sample_id,
            "target_sequence": result.target_sequence,
            "editing_efficiency": result.editing_efficiency,
            "deletion_pct": result.deletion_pct,
            "insertion_pct": result.insertion_pct,
            "wt_pct": result.wt_pct,
            "indel_summary": result.indel_summary,
            "report_dir": result.report_dir,
        }


class ICEBatchAnalyzer:
    """ICE 批量分析器"""

    def __init__(
        self,
        excel_file: Path,
        data_dir: Path,
        output_dir: Optional[Path] = None,
    ):
        """
        初始化批量分析器

        Args:
            excel_file: Excel 定义文件
            data_dir: .ab1 文件所在目录
            output_dir: 输出目录
        """
        self.excel_file = Path(excel_file)
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir) if output_dir else self.data_dir / "ice_results"

    def run(self) -> list[ICEResult]:
        """
        执行批量分析

        Returns:
            ICEResult 列表
        """
        cmd = [
            "synthego_ice_batch",
            "--in", str(self.excel_file),
            "--data", str(self.data_dir),
            "--out", str(self.output_dir),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ICE 批量分析失败: {result.stderr}")

        # 解析所有样本结果
        results = []
        for sample_dir in self.output_dir.iterdir():
            if sample_dir.is_dir():
                # 读取每个样本的结果
                indel_file = sample_dir / f"{sample_dir.name}_indel.json"
                if indel_file.exists():
                    # 简化处理，实际应从 Excel 读取 target
                    results.append(
                        ICEResult(
                            sample_id=sample_dir.name,
                            target_sequence="",
                            editing_efficiency=0.0,
                            report_dir=str(sample_dir),
                        )
                    )

        return results


def save_results_to_db(
    project_name: str,
    results: list[ICEResult],
    output_dir: Path,
    input_file: Optional[Path] = None,
    failed_samples: Optional[list[str]] = None,
) -> int:
    """
    保存结果到数据库

    Returns:
        run_id
    """
    import shutil

    sys.path.insert(0, str(ROOT))
    from scripts.db import DB
    from scripts.files import Files

    # 确保 schema 已安装
    skill_meta_dir = SKILL_DIR.parent / "meta"
    project_meta_dir = ROOT / "meta"
    project_meta_dir.mkdir(exist_ok=True)

    for schema_file in skill_meta_dir.glob("*.json"):
        dest = project_meta_dir / schema_file.name
        if not dest.exists():
            shutil.copy(schema_file, dest)

    db = DB()
    files = Files()

    # 创建运行记录
    db.ensure_table("ice_run")
    run_data = {
        "project_name": project_name,
        "input_file": str(input_file) if input_file else None,
        "total_samples": len(results) + len(failed_samples or []),
        "success_samples": len(results),
        "failed_samples": json.dumps(failed_samples) if failed_samples else None,
        "output_dir": str(output_dir),
        "run_date": datetime.now().strftime("%Y-%m-%d"),
    }
    run_id = db.insert("data_ice_run", run_data)
    print(f"运行记录已保存: run_id={run_id}")

    # 创建样本结果记录
    db.ensure_table("ice_result")

    for result in results:
        # 归档报告目录
        report_archive = None
        if result.report_dir and Path(result.report_dir).exists():
            # 归档关键文件
            report_archive = str(result.report_dir)

        sample_data = {
            "run_id": run_id,
            "sample_id": result.sample_id,
            "control_file": None,  # 需要从输入获取
            "edited_file": None,
            "target_sequence": result.target_sequence,
            "editing_efficiency": result.editing_efficiency,
            "deletion_pct": result.deletion_pct,
            "insertion_pct": result.insertion_pct,
            "wt_pct": result.wt_pct,
            "indel_summary": json.dumps(result.indel_summary) if result.indel_summary else None,
            "report_file": report_archive,
        }
        db.insert("data_ice_result", sample_data)

    print(f"样本结果已保存: {len(results)} 条")
    return run_id


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ICE CRISPR 编辑分析")
    parser.add_argument("--control", "-c", help="对照样本 .ab1 文件")
    parser.add_argument("--edited", "-e", help="编辑样本 .ab1 文件")
    parser.add_argument("--target", "-t", help="gRNA 目标序列")
    parser.add_argument("--output", "-o", help="输出目录")
    parser.add_argument("--batch", "-b", help="批量分析 Excel 文件")
    parser.add_argument("--data", "-d", help="数据目录（批量分析用）")
    parser.add_argument("--project", "-p", help="项目名称")
    parser.add_argument("--no-db", action="store_true", help="不保存到数据库")

    args = parser.parse_args()

    if args.batch:
        # 批量分析
        analyzer = ICEBatchAnalyzer(
            excel_file=Path(args.batch),
            data_dir=Path(args.data),
            output_dir=Path(args.output) if args.output else None,
        )
        results = analyzer.run()
    elif args.control and args.edited and args.target:
        # 单样本分析
        analyzer = ICEAnalyzer(
            control=Path(args.control),
            edited=Path(args.edited),
            target=args.target,
            output_dir=Path(args.output) if args.output else None,
        )
        result = analyzer.run()

        print(f"\n样本: {result.sample_id}")
        print(f"目标序列: {result.target_sequence}")
        print(f"编辑效率: {result.editing_efficiency}%")
        print(f"  - 缺失: {result.deletion_pct}%")
        print(f"  - 插入: {result.insertion_pct}%")
        print(f"  - 野生型: {result.wt_pct}%")

        results = [result]
    else:
        parser.print_help()
        sys.exit(1)

    # 保存到数据库
    if not args.no_db and results:
        save_results_to_db(
            project_name=args.project or "ice_analysis",
            results=results,
            output_dir=Path(args.output) if args.output else Path("."),
        )
