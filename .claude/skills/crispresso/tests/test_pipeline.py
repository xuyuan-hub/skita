"""
CRISPResso Pipeline Tests - GOA_8 Test Case

All test data lives inside the skill directory: tests/data/GOA_8/
Large files (FASTQ, genomes) are excluded from Git.
Contact 2827883762@qq.com to obtain test data and reference files.

Test categories:
- TestPreprocess: Stage 1 only, no Docker required
- TestFullPipeline: Requires Docker + CRISPResso2 image
- TestMutationInterpretation: Mutation interpretation, auto-fallback to full pipeline output
"""

import os
import sys
import shutil
import pytest
from pathlib import Path

# All paths relative to skill directory (self-contained)
SKILL_DIR = Path(__file__).resolve().parents[1]  # tests/ -> crispresso/
SCRIPTS_DIR = SKILL_DIR / "scripts"
TEST_DATA_DIR = SKILL_DIR / "tests" / "data" / "GOA_8"

# Add scripts to path for pipeline imports
sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline.runner import Pipeline, PipelineConfig
from pipeline.locus_filter import filter_locus

# Reference files (inside skill)
REF_GENOME = SKILL_DIR / "genomes" / "all.con"
REF_DB = SKILL_DIR / "genomes" / "all.locus_brief_info.7.0"

# Test data (inside skill)
GOA8_CSV = TEST_DATA_DIR / "GOA_8.csv"
GOA8_R1 = TEST_DATA_DIR / "GOA_8_HQ_R1.fq.gz"
GOA8_R2 = TEST_DATA_DIR / "GOA_8_HQ_R2.fq.gz"
GOA8_RESULTS_TXT = TEST_DATA_DIR / "GOA_8_Results_Txt"

SKIP_MSG = "测试数据缺失，请联系 2827883762@qq.com 获取"

# Expected values from verified run
EXPECTED_TOTAL_SAMPLES = 56
EXPECTED_SGRNA_FOUND = 56
EXPECTED_AMPLICON_LINES = 56
EXPECTED_RESULT_FILES = 50
EXPECTED_MISSING_SAMPLES = {
    "BG8823-8", "BG8837-8", "BG9281-8", "BG9417-8", "BG9459-8", "BG9477-8"
}

# Expected mutation results (sample -> interpretation)
EXPECTED_MUTATIONS = {
    "BG8875-8": "无突变",
    "BG9339-8": "无突变",
    "BG9356-8": "无突变",
    "BG9389-8": "无突变",
    "BG9396-8": "无突变",
    "BG9456-8": "无突变",
    "BG8832-8": "双等位突变，T插入/A插入",
    "BG9390-8": "双等位突变，10bp缺失/5bp缺失",
    "BG9391-8": "双等位突变，A缺失/T插入",
    "BG9358-8": "杂合突变，WT/TC插入",
}


def _check_ref_files():
    """Check if reference genome files exist."""
    missing = []
    if not REF_GENOME.exists():
        missing.append("genomes/all.con")
    if not REF_DB.exists():
        missing.append("genomes/all.locus_brief_info.7.0")
    return missing


def _check_docker():
    """Check if Docker is running and CRISPResso2 image is available."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return "Docker is not running"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "Docker is not installed or not responding"

    result = subprocess.run(
        ["docker", "images", "pinellolab/crispresso2", "--format", "{{.Repository}}"],
        capture_output=True, text=True, timeout=10,
    )
    if "pinellolab/crispresso2" not in result.stdout:
        return "CRISPResso2 image not found. Run: docker pull pinellolab/crispresso2:latest"
    return None


def _check_pipeline_prerequisites():
    """Check all prerequisites for running the full pipeline. Returns skip reason or None."""
    if not GOA8_CSV.exists():
        return f"{SKIP_MSG}: GOA_8.csv"
    ref_missing = _check_ref_files()
    if ref_missing:
        return f"{SKIP_MSG}: {', '.join(ref_missing)}"
    if not GOA8_R1.exists() or not GOA8_R2.exists():
        return f"{SKIP_MSG}: FASTQ files"
    docker_err = _check_docker()
    if docker_err:
        return docker_err
    return None


# --- Session-scoped fixture: full pipeline run (shared across TestFullPipeline and TestMutationInterpretation) ---

_full_pipeline_cache = {}


@pytest.fixture(scope="session")
def full_pipeline_results_txt(tmp_path_factory):
    """Run full pipeline once per session, return path to Results_Txt directory.

    Result is shared between TestFullPipeline and TestMutationInterpretation.
    """
    skip_reason = _check_pipeline_prerequisites()
    if skip_reason:
        pytest.skip(skip_reason)

    output_dir = tmp_path_factory.mktemp("goa8_full")
    config = PipelineConfig(
        r1=GOA8_R1,
        r2=GOA8_R2,
        csv=GOA8_CSV,
        project_name="GOA_8",
        output_dir=output_dir,
        ref_genome=REF_GENOME,
        ref_db=REF_DB,
    )

    logs = []
    pipeline = Pipeline(config=config, log_callback=lambda msg: logs.append(msg))
    success = pipeline.run()

    work_dir = output_dir / "GOA_8"
    result = {
        "success": success,
        "logs": logs,
        "work_dir": work_dir,
        "results_txt": work_dir / "GOA_8_Results_Txt",
        "results_png": work_dir / "GOA_8_Results_Png",
    }
    _full_pipeline_cache.update(result)
    return result


# --- Fixtures ---

@pytest.fixture(scope="module")
def preprocess_output(tmp_path_factory):
    """Run Stage 1 (preprocess) once and share results across tests."""
    if not GOA8_CSV.exists():
        pytest.skip(f"{SKIP_MSG}: tests/data/GOA_8/GOA_8.csv")

    ref_missing = _check_ref_files()
    if ref_missing:
        pytest.skip(f"{SKIP_MSG}: {', '.join(ref_missing)}")

    if not GOA8_R1.exists() or not GOA8_R2.exists():
        pytest.skip(f"{SKIP_MSG}: FASTQ files (GOA_8_HQ_R1/R2.fq.gz)")

    output_dir = tmp_path_factory.mktemp("goa8_preprocess")
    config = PipelineConfig(
        r1=GOA8_R1,
        r2=GOA8_R2,
        csv=GOA8_CSV,
        project_name="GOA_8",
        output_dir=output_dir,
        ref_genome=REF_GENOME,
        ref_db=REF_DB,
    )

    logs = []
    pipeline = Pipeline(config=config, log_callback=lambda msg: logs.append(msg))
    success = pipeline.stage1_preprocess()

    return {
        "success": success,
        "pipeline": pipeline,
        "config": config,
        "logs": logs,
        "work_dir": output_dir / "GOA_8",
    }


# --- Stage 1: Preprocess Tests (No Docker Required) ---

class TestPreprocess:
    """Test Stage 1: Preprocessing (locus filter, sequence extraction, sgRNA location)."""

    def test_preprocess_succeeds(self, preprocess_output):
        """Stage 1 should complete successfully."""
        assert preprocess_output["success"], (
            f"Stage 1 failed. Logs:\n" + "\n".join(preprocess_output["logs"])
        )

    def test_sgrna_all_found(self, preprocess_output):
        """All 56 sgRNA sequences should be found in the reference genome."""
        pipeline = preprocess_output["pipeline"]
        assert pipeline.sgrna_matches is not None

        found_count = sum(1 for m in pipeline.sgrna_matches if m.found)
        assert found_count == EXPECTED_SGRNA_FOUND, (
            f"Expected {EXPECTED_SGRNA_FOUND} sgRNA matches, got {found_count}"
        )

    def test_amplicon_file_created(self, preprocess_output):
        """amplicon.txt should be created with 56 entries."""
        pipeline = preprocess_output["pipeline"]
        assert pipeline.amplicon_file is not None
        assert pipeline.amplicon_file.exists()

        with open(pipeline.amplicon_file) as f:
            line_count = sum(1 for _ in f)
        assert line_count == EXPECTED_AMPLICON_LINES, (
            f"Expected {EXPECTED_AMPLICON_LINES} amplicon lines, got {line_count}"
        )

    def test_amplicon_format(self, preprocess_output):
        """Each amplicon line should have 5 tab-separated fields: GeoID, seq, target, empty, empty."""
        pipeline = preprocess_output["pipeline"]
        with open(pipeline.amplicon_file) as f:
            for i, line in enumerate(f, 1):
                fields = line.rstrip("\n").split("\t")
                assert len(fields) == 5, (
                    f"Line {i}: expected 5 fields, got {len(fields)}: {line!r}"
                )
                geo_id, seq, target = fields[0], fields[1], fields[2]
                assert len(target) == 23, (
                    f"Line {i}: target should be 23bp, got {len(target)}"
                )
                assert len(seq) > 100, (
                    f"Line {i}: amplicon seq too short ({len(seq)}bp)"
                )

    def test_locus_filter_count(self):
        """Locus filter should find 56 loci from GOA_8.csv."""
        if not GOA8_CSV.exists():
            pytest.skip(f"{SKIP_MSG}: GOA_8.csv")
        ref_missing = _check_ref_files()
        if ref_missing:
            pytest.skip(f"{SKIP_MSG}: {', '.join(ref_missing)}")

        result = filter_locus(GOA8_CSV, REF_DB)
        assert len(result.bed_data) == EXPECTED_TOTAL_SAMPLES, (
            f"Expected {EXPECTED_TOTAL_SAMPLES} loci, got {len(result.bed_data)}"
        )


# --- Full Pipeline Tests (Requires Docker) ---

class TestFullPipeline:
    """Test full pipeline including Docker CRISPResso2 execution.

    Requires: Docker + CRISPResso2 image + FASTQ files + reference genomes.
    """

    def test_pipeline_succeeds(self, full_pipeline_results_txt):
        """Full pipeline should complete successfully."""
        assert full_pipeline_results_txt["success"], (
            f"Pipeline failed. Logs:\n" + "\n".join(full_pipeline_results_txt["logs"][-20:])
        )

    def test_result_txt_count(self, full_pipeline_results_txt):
        """Should collect exactly 50 TXT result files."""
        results_txt = full_pipeline_results_txt["results_txt"]
        assert results_txt.exists(), f"Results dir not found: {results_txt}"

        txt_files = list(results_txt.glob("*.txt"))
        assert len(txt_files) == EXPECTED_RESULT_FILES, (
            f"Expected {EXPECTED_RESULT_FILES} result files, got {len(txt_files)}"
        )

    def test_result_png_count(self, full_pipeline_results_txt):
        """Should collect exactly 50 PNG result files."""
        results_png = full_pipeline_results_txt["results_png"]
        assert results_png.exists(), f"PNG dir not found: {results_png}"

        png_files = list(results_png.glob("*.png"))
        assert len(png_files) == EXPECTED_RESULT_FILES, (
            f"Expected {EXPECTED_RESULT_FILES} PNG files, got {len(png_files)}"
        )

    def test_missing_samples(self, full_pipeline_results_txt):
        """The 6 known missing samples should not have result files."""
        results_txt = full_pipeline_results_txt["results_txt"]
        if not results_txt.exists():
            pytest.skip("Results directory not found")

        result_ids = {f.stem for f in results_txt.glob("*.txt")}
        for sample_id in EXPECTED_MISSING_SAMPLES:
            assert sample_id not in result_ids, (
                f"Sample {sample_id} should NOT have a result file"
            )


# --- Mutation Interpretation Tests ---

class TestMutationInterpretation:
    """Test mutation_define_NGS.py against known GOA_8 results.

    Data source priority:
    1. Pre-existing results in tests/data/GOA_8/GOA_8_Results_Txt/ (golden data)
    2. Full pipeline output from TestFullPipeline (auto-fallback)
    If neither is available, tests are skipped.
    """

    @pytest.fixture()
    def results_txt_dir(self, full_pipeline_results_txt):
        """Resolve the Results_Txt directory: prefer pre-existing golden data, fallback to pipeline output."""
        if GOA8_RESULTS_TXT.exists() and list(GOA8_RESULTS_TXT.glob("*.txt")):
            return GOA8_RESULTS_TXT

        # Fallback: use full pipeline output
        pipeline_txt = full_pipeline_results_txt["results_txt"]
        if pipeline_txt.exists() and list(pipeline_txt.glob("*.txt")):
            return pipeline_txt

        pytest.skip("无可用的 Results_Txt 数据（预存数据和 pipeline 输出均不存在）")

    def test_mutation_results_exist(self, results_txt_dir):
        """Result TXT files should exist (from golden data or pipeline output)."""
        txt_files = list(results_txt_dir.glob("*.txt"))
        assert len(txt_files) == EXPECTED_RESULT_FILES

    def test_mutation_output_file(self, results_txt_dir, tmp_path):
        """mutation_define_NGS.py should generate a TSV output file."""
        # Copy results to tmp dir to avoid modifying original
        test_results_dir = tmp_path / "GOA_8" / "GOA_Results_Txt"
        test_results_dir.mkdir(parents=True)
        for f in results_txt_dir.glob("*.txt"):
            shutil.copy(f, test_results_dir / f.name)

        from mutation_define_NGS import process_all_txt_files
        output_path = process_all_txt_files(str(test_results_dir))

        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == EXPECTED_RESULT_FILES, (
            f"Expected {EXPECTED_RESULT_FILES} mutation lines, got {len(lines)}"
        )

    def test_mutation_no_mutation_count(self, results_txt_dir, tmp_path):
        """Should identify exactly 6 samples with no mutation."""
        test_results_dir = tmp_path / "GOA_8" / "GOA_Results_Txt"
        test_results_dir.mkdir(parents=True)
        for f in results_txt_dir.glob("*.txt"):
            shutil.copy(f, test_results_dir / f.name)

        from mutation_define_NGS import process_all_txt_files
        output_path = process_all_txt_files(str(test_results_dir))

        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()

        no_mutation = [l for l in lines if "无突变" in l]
        assert len(no_mutation) == 6, (
            f"Expected 6 no-mutation samples, got {len(no_mutation)}"
        )

    def test_mutation_specific_results(self, results_txt_dir, tmp_path):
        """Key mutation interpretations should match expected values."""
        test_results_dir = tmp_path / "GOA_8" / "GOA_Results_Txt"
        test_results_dir.mkdir(parents=True)
        for f in results_txt_dir.glob("*.txt"):
            shutil.copy(f, test_results_dir / f.name)

        from mutation_define_NGS import process_all_txt_files
        output_path = process_all_txt_files(str(test_results_dir))

        # Parse results into dict
        results = {}
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t", 1)
                if len(parts) == 2:
                    results[parts[0]] = parts[1]

        # Verify each expected mutation
        for sample_id, expected in EXPECTED_MUTATIONS.items():
            assert sample_id in results, (
                f"Sample {sample_id} not found in mutation results"
            )
            actual = results[sample_id]
            assert actual == expected, (
                f"Sample {sample_id}: expected '{expected}', got '{actual}'"
            )

    def test_describe_sequence_variation_wt(self):
        """WT sequence (no indels) should return WT description."""
        from mutation_define_NGS import describe_sequence_variation
        desc, is_frameshift = describe_sequence_variation("ATCGATCG", "ATCGATCG")
        assert desc == "WT"
        assert is_frameshift is False

    def test_describe_sequence_variation_deletion(self):
        """Single base deletion should be described with the deleted base."""
        from mutation_define_NGS import describe_sequence_variation
        desc, is_frameshift = describe_sequence_variation("ATC-ATCG", "ATCGATCG")
        assert "缺失" in desc
        assert is_frameshift is True

    def test_describe_sequence_variation_insertion(self):
        """Single base insertion should be described with the inserted base."""
        from mutation_define_NGS import describe_sequence_variation
        desc, is_frameshift = describe_sequence_variation("ATCGATCG", "ATC-ATCG")
        assert "插入" in desc
        assert is_frameshift is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
