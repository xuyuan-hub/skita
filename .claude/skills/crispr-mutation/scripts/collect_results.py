#!/usr/bin/env python3
"""
Collect CRISPResso analysis results (TXT and PNG files) from existing runs.

Usage:
    uv run python .claude/skills/crispr-mutation/scripts/collect_results.py <project_dir> [--txt] [--png] [--all]

Examples:
    # Collect PNG files only
    uv run python .claude/skills/crispr-mutation/scripts/collect_results.py output/SA --png

    # Collect TXT files only
    uv run python .claude/skills/crispr-mutation/scripts/collect_results.py output/SA --txt

    # Collect both
    uv run python .claude/skills/crispr-mutation/scripts/collect_results.py output/SA --all
"""

import argparse
import shutil
from pathlib import Path


def collect_txt_results(pool_dir: Path, output_dir: Path) -> int:
    """
    Collect allele frequency TXT files from CRISPResso results.

    Args:
        pool_dir: Path to CRISPRessoPooled_on_* directory
        output_dir: Path to output directory for collected files

    Returns:
        Number of files collected
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    copied_count = 0

    for sample_dir in pool_dir.glob("CRISPResso_on_*"):
        if not sample_dir.is_dir():
            continue

        sample_name = sample_dir.name.replace("CRISPResso_on_", "")

        # Find allele frequency table TXT
        txt_files = list(sample_dir.glob("*Alleles_frequency_table_around_sgRNA*txt"))
        if txt_files:
            src_file = txt_files[0]
            dst_file = output_dir / f"{sample_name}.txt"
            shutil.copy(src_file, dst_file)
            copied_count += 1

    return copied_count


def collect_png_results(pool_dir: Path, output_dir: Path) -> int:
    """
    Collect allele frequency PNG files from CRISPResso results.

    Args:
        pool_dir: Path to CRISPRessoPooled_on_* directory
        output_dir: Path to output directory for collected files

    Returns:
        Number of files collected
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    copied_count = 0

    for sample_dir in pool_dir.glob("CRISPResso_on_*"):
        if not sample_dir.is_dir():
            continue

        sample_name = sample_dir.name.replace("CRISPResso_on_", "")

        # Find allele frequency table PNG
        png_files = list(sample_dir.glob("*Alleles_frequency_table*.png"))
        if png_files:
            src_file = png_files[0]
            dst_file = output_dir / f"{sample_name}.png"
            shutil.copy(src_file, dst_file)
            copied_count += 1

    return copied_count


def main():
    parser = argparse.ArgumentParser(
        description="Collect CRISPResso analysis results"
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to project directory (e.g., output/SA)",
    )
    parser.add_argument(
        "--txt",
        action="store_true",
        help="Collect TXT allele frequency tables",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Collect PNG allele frequency images",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Collect both TXT and PNG files",
    )

    args = parser.parse_args()

    project_dir = args.project_dir.resolve()

    if not project_dir.exists():
        print(f"Error: Project directory not found: {project_dir}")
        return 1

    # Find CRISPRessoPooled directory
    pool_dirs = list(project_dir.glob("CRISPRessoPooled_on_*"))
    if not pool_dirs:
        print(f"Error: No CRISPRessoPooled_on_* directory found in {project_dir}")
        return 1

    pool_dir = pool_dirs[0]
    print(f"Found pool directory: {pool_dir}")

    # Get project name from directory name
    project_name = project_dir.name

    # Determine what to collect
    collect_txt = args.txt or args.all
    collect_png = args.png or args.all

    if not collect_txt and not collect_png:
        print("Error: Specify --txt, --png, or --all")
        return 1

    # Collect TXT files
    if collect_txt:
        txt_dir = project_dir / f"{project_name}_Results_Txt"
        txt_count = collect_txt_results(pool_dir, txt_dir)
        print(f"Collected {txt_count} TXT files to: {txt_dir}")

    # Collect PNG files
    if collect_png:
        png_dir = project_dir / f"{project_name}_Results_Png"
        png_count = collect_png_results(pool_dir, png_dir)
        print(f"Collected {png_count} PNG files to: {png_dir}")

    print("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
