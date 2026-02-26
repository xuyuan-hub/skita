#!/usr/bin/env python3
"""
Batch run CRISPResso analysis for multiple samples.

Usage:
    python .claude/skills/crispresso/scripts/batch_run.py --data-dir data/26_01_28 --samples SA_30,SB_19
    python .claude/skills/crispresso/scripts/batch_run.py --data-dir data/26_01_28 --all
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Add scripts directory to sys.path so 'pipeline' package can be found
# This makes the skill self-contained and portable across projects
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pipeline.runner import Pipeline, PipelineConfig


def get_samples_from_directory(hq_data_dir: Path) -> list[str]:
    """Get list of sample names from HQ data directory."""
    samples = []
    for r1 in sorted(hq_data_dir.glob("*_HQ_R1.fq.gz")):
        name = r1.name.replace("_HQ_R1.fq.gz", "")
        samples.append(name)
    return samples


def run_crispresso_docker(
    r1: Path,
    r2: Path,
    amplicon_file: Path,
    output_dir: Path,
    name: str = "amp_aa",
) -> bool:
    """Run CRISPRessoPooled via Docker with proper Windows path handling."""

    # Prepare environment for Windows
    env = os.environ.copy()
    if platform.system() == "Windows":
        env["MSYS_NO_PATHCONV"] = "1"

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{output_dir}:/DATA",
        "-v", f"{r1.parent}:/INPUT:ro",
        "pinellolab/crispresso2:latest",
        "CRISPRessoPooled",
        "-r1", f"/INPUT/{r1.name}",
        "-r2", f"/INPUT/{r2.name}",
        "-f", f"/DATA/{amplicon_file.name}",
        "--name", name,
        "-p", "max",
        "--output_folder", "/DATA",
    ]

    print(f"Running CRISPRessoPooled for {name}...")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=False,
            text=True,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error running CRISPResso: {e}")
        return False


def collect_results(pool_dir: Path, results_dir: Path) -> int:
    """Collect allele frequency tables from CRISPResso output."""
    results_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for sample_dir in pool_dir.glob("CRISPResso_on_*"):
        if not sample_dir.is_dir():
            continue

        sample_name = sample_dir.name.replace("CRISPResso_on_", "")
        freq_files = list(sample_dir.glob("*Alleles_frequency_table_around_sgRNA*txt"))

        if freq_files:
            src_file = freq_files[0]
            dst_file = results_dir / f"{sample_name}.txt"
            shutil.copy(src_file, dst_file)
            copied_count += 1

    return copied_count


def run_sample(
    sample_name: str,
    data_dir: Path,
    csv_file: Path,
    ref_genome: Path,
    ref_db: Path,
) -> bool:
    """Run full pipeline for a single sample."""

    hq_data_dir = data_dir / "data" / "2_HQData"
    result_dir = data_dir / "result"

    r1 = hq_data_dir / f"{sample_name}_HQ_R1.fq.gz"
    r2 = hq_data_dir / f"{sample_name}_HQ_R2.fq.gz"

    if not r1.exists() or not r2.exists():
        print(f"Error: FASTQ files not found for {sample_name}")
        return False

    print(f"\n{'='*60}")
    print(f"Processing sample: {sample_name}")
    print(f"{'='*60}")

    # Create pipeline config
    config = PipelineConfig(
        r1=r1,
        r2=r2,
        csv=csv_file,
        project_name=sample_name,
        output_dir=result_dir,
        ref_genome=ref_genome,
        ref_db=ref_db,
    )

    # Run preprocessing (Stage 1)
    pipeline = Pipeline(config=config, log_callback=print)

    print("\n>>> Stage 1: Preprocessing...")
    if not pipeline.stage1_preprocess():
        print(f"Stage 1 failed for {sample_name}")
        return False

    # Run CRISPResso (Stage 2) via Docker
    print("\n>>> Stage 2: CRISPRessoPooled...")
    work_dir = result_dir / sample_name
    amplicon_file = work_dir / "amplicon.txt"

    if not run_crispresso_docker(r1, r2, amplicon_file, work_dir):
        print(f"Stage 2 failed for {sample_name}")
        # Continue to collect partial results

    # Collect results (Stage 4)
    print("\n>>> Stage 4: Collecting results...")
    pool_dir = work_dir / "CRISPRessoPooled_on_amp_aa"
    results_dir = work_dir / f"{sample_name}_Results_Txt"

    if pool_dir.exists():
        count = collect_results(pool_dir, results_dir)
        print(f"Collected {count} result files")
        print(f"Results saved to: {results_dir}")
        return count > 0
    else:
        print("No CRISPResso output found")
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch run CRISPResso analysis")
    parser.add_argument("--data-dir", type=Path, required=True,
                       help="Data directory containing samples.csv and data/2_HQData/")
    parser.add_argument("--samples", type=str,
                       help="Comma-separated list of sample names to process")
    parser.add_argument("--all", action="store_true",
                       help="Process all samples found in data directory")
    # Default reference files: use skill's own genomes/ directory
    _SKILL_DIR = Path(__file__).resolve().parent.parent
    _DEFAULT_GENOME = _SKILL_DIR / "genomes" / "all.con"
    _DEFAULT_DB = _SKILL_DIR / "genomes" / "all.locus_brief_info.7.0"

    parser.add_argument("--ref-genome", type=Path, default=_DEFAULT_GENOME,
                       help="Reference genome file (default: skill's genomes/all.con)")
    parser.add_argument("--ref-db", type=Path, default=_DEFAULT_DB,
                       help="Reference database file (default: skill's genomes/all.locus_brief_info.7.0)")

    args = parser.parse_args()

    # Find CSV file
    csv_file = args.data_dir / "samples.csv"
    if not csv_file.exists():
        print(f"Error: CSV file not found: {csv_file}")
        return 1

    # Get samples to process
    hq_data_dir = args.data_dir / "data" / "2_HQData"

    if args.all:
        samples = get_samples_from_directory(hq_data_dir)
    elif args.samples:
        samples = [s.strip() for s in args.samples.split(",")]
    else:
        print("Error: Specify --samples or --all")
        return 1

    print(f"Samples to process: {samples}")

    # Process each sample
    results = {}
    for sample in samples:
        success = run_sample(
            sample_name=sample,
            data_dir=args.data_dir,
            csv_file=csv_file,
            ref_genome=args.ref_genome,
            ref_db=args.ref_db,
        )
        results[sample] = success

    # Print summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    for sample, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {sample}: {status}")

    success_count = sum(1 for s in results.values() if s)
    print(f"\nTotal: {success_count}/{len(results)} samples completed successfully")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    exit(main())
