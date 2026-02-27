"""
Pipeline Runner - Main Controller

Replaces run_pipeline.sh with a pure Python implementation.
Orchestrates all stages of the CRISPResso analysis pipeline.
"""

import shutil
from pathlib import Path
from typing import Callable
from dataclasses import dataclass

import pandas as pd

from .locus_filter import filter_locus, FilterResult
from .sequence_extractor import SequenceExtractor, extract_sequences_to_dict
from .sgrna_locator import (
    locate_sgrna,
    matches_to_dataframe,
    get_sgrna_bed_coordinates,
    get_amplicon_bed_coordinates,
    build_amplicon_sequences,
    build_amplicon_from_direct_extraction,
    SgRNAMatch,
)
from .crispresso import CRISPRessoDocker, CRISPRessoResult


@dataclass
class PipelineConfig:
    """Configuration for the pipeline."""
    r1: Path
    r2: Path
    csv: Path
    project_name: str
    output_dir: Path
    ref_genome: Path
    ref_db: Path
    seq_length: int = 150
    save_to_db: bool = True


class Pipeline:
    """
    Main pipeline controller.

    Orchestrates all stages:
    1. Preprocess: Filter locus, extract sequences, locate sgRNA
    2. CRISPRessoPooled: Run pooled analysis
    3. Retry: Re-run failed samples
    4. Collect: Gather results
    """

    def __init__(
        self,
        config: PipelineConfig,
        log_callback: Callable[[str], None] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
    ):
        """
        Initialize pipeline.

        Args:
            config: Pipeline configuration
            log_callback: Callback for log messages (message: str)
            progress_callback: Callback for progress updates (stage: str, percent: int)
        """
        self.config = config
        self.log_callback = log_callback
        self.progress_callback = progress_callback

        # Work directory
        self.work_dir = config.output_dir / config.project_name
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # CRISPResso Docker wrapper
        self.crispresso = CRISPRessoDocker(log_callback=self._log)

        # State
        self.filter_result: FilterResult | None = None
        self.sgrna_matches: list[SgRNAMatch] | None = None
        self.amplicon_file: Path | None = None
        self.pool_dir: Path | None = None

    def _log(self, message: str):
        """Send log message."""
        if self.log_callback:
            self.log_callback(message)

    def _progress(self, stage: str, percent: int):
        """Send progress update."""
        if self.progress_callback:
            self.progress_callback(stage, percent)

    def validate_inputs(self) -> bool:
        """Validate all input files exist."""
        errors = []

        if not self.config.r1.exists():
            errors.append(f"R1 file not found: {self.config.r1}")
        if not self.config.r2.exists():
            errors.append(f"R2 file not found: {self.config.r2}")
        if not self.config.csv.exists():
            errors.append(f"CSV file not found: {self.config.csv}")
        if not self.config.ref_genome.exists():
            errors.append(f"Reference genome not found: {self.config.ref_genome}")
        if not self.config.ref_db.exists():
            errors.append(f"Reference database not found: {self.config.ref_db}")

        if errors:
            for err in errors:
                self._log(f"[ERROR] {err}")
            return False

        return True

    def stage1_preprocess(self) -> bool:
        """
        Stage 1: Preprocess data.

        Following the original bash script logic:
        1. Filter locus from reference database (replaces 1-new.R)
        2. Extract sequences from reference genome (replaces bedtools getfasta)
        3. Locate sgRNA in sequences (replaces extract_fasta.py)
        4. Extract full amplicon regions directly from genome
        5. Generate amplicon.txt file for CRISPResso
        """
        self._log(">>> [Stage 1] Preprocessing...")
        self._progress("preprocess", 0)

        try:
            # Step 1.1: Filter locus
            self._log(">>> Filtering locus from reference database...")
            self.filter_result = filter_locus(
                input_csv=self.config.csv,
                ref_db=self.config.ref_db,
            )
            self._log(f"    Found {len(self.filter_result.bed_data)} loci")
            self._progress("preprocess", 20)

            # Step 1.2: Extract sequences from locus regions
            self._log(">>> Extracting locus sequences from reference genome...")
            with SequenceExtractor(self.config.ref_genome) as extractor:
                sequences = extractor.extract_from_bed(self.filter_result.bed_data)
            self._log(f"    Extracted {len(sequences)} sequences")
            self._progress("preprocess", 40)

            # Step 1.3: Locate sgRNA in sequences
            self._log(">>> Locating sgRNA in sequences...")
            self.sgrna_matches = locate_sgrna(
                sequences=sequences,
                metadata=self.filter_result.metadata,
                seq_length=self.config.seq_length,
            )

            found_count = sum(1 for m in self.sgrna_matches if m.found)
            self._log(f"    Found sgRNA in {found_count}/{len(self.sgrna_matches)} sequences")
            self._progress("preprocess", 60)

            if found_count == 0:
                self._log("[ERROR] No valid sgRNA matches found")
                return False

            # Step 1.4: Get amplicon BED coordinates and extract sequences
            self._log(">>> Extracting amplicon sequences...")
            amplicon_bed = get_amplicon_bed_coordinates(self.sgrna_matches)

            if amplicon_bed.empty:
                self._log("[ERROR] No amplicon coordinates generated")
                return False

            # Extract amplicon sequences directly from the genome
            # This matches the bash script's approach of extracting the full region
            with SequenceExtractor(self.config.ref_genome) as extractor:
                amplicon_seqs = {}
                for _, row in amplicon_bed.iterrows():
                    # Key format: "Chr1:12345-12698" (matching amplicon_coord)
                    key = f"{row['chr']}:{row['start']}-{row['stop']}"
                    amplicon_seqs[key] = extractor.extract_sequence(
                        row["chr"], int(row["start"]), int(row["stop"])
                    )

            self._log(f"    Extracted {len(amplicon_seqs)} amplicon sequences")
            self._progress("preprocess", 80)

            # Step 1.5: Build amplicon data using direct extraction
            self._log(">>> Building amplicon data...")
            amplicon_df = build_amplicon_from_direct_extraction(
                self.sgrna_matches,
                amplicon_seqs,
            )

            if amplicon_df.empty:
                self._log("[ERROR] No amplicon data generated")
                return False

            self._log(f"    Built {len(amplicon_df)} amplicon entries")

            # Step 1.6: Generate amplicon.txt
            self._log(">>> Generating amplicon.txt...")
            self.amplicon_file = self._generate_amplicon_file_v2(amplicon_df)

            if self.amplicon_file and self.amplicon_file.exists():
                # Verify file is not empty
                with open(self.amplicon_file, 'r') as f:
                    line_count = sum(1 for _ in f)
                if line_count == 0:
                    self._log("[ERROR] amplicon.txt is empty")
                    return False
                self._log(f"    Amplicon file: {self.amplicon_file} ({line_count} entries)")
                self._progress("preprocess", 100)
                return True
            else:
                self._log("[ERROR] Failed to generate amplicon.txt")
                return False

        except Exception as e:
            self._log(f"[ERROR] Stage 1 failed: {e}")
            import traceback
            self._log(traceback.format_exc())
            return False

    def _generate_amplicon_file(self, amplicon_df: pd.DataFrame) -> Path:
        """Generate amplicon.txt file for CRISPResso (legacy method)."""
        # Read original input to get GeoID mapping
        input_df = pd.read_csv(
            self.config.csv, header=None, names=["GeoID", "Locus", "Target"]
        )
        if input_df.iloc[0]["GeoID"] == "GeoID":
            input_df = input_df.iloc[1:].reset_index(drop=True)

        # Build amplicon file rows
        rows = []
        for _, amp_row in amplicon_df.iterrows():
            # Find matching input row by sgRNA sequence
            sg_seq = amp_row["sg_seq"]
            matching = input_df[input_df["Target"] == sg_seq]

            if matching.empty:
                # Try reverse complement
                from Bio.Seq import Seq
                sg_rev = str(Seq(sg_seq).reverse_complement())
                matching = input_df[input_df["Target"] == sg_rev]

            if not matching.empty:
                geo_id = matching.iloc[0]["GeoID"]
                target = matching.iloc[0]["Target"]
                rows.append({
                    "GeoID": geo_id,
                    "seq": amp_row["amplicon_seq"],
                    "Target": target,
                    "i1": "",
                    "i2": "",
                })

        # Save amplicon file
        amplicon_path = self.work_dir / "amplicon.txt"
        amplicon_df_out = pd.DataFrame(rows)
        amplicon_df_out.to_csv(amplicon_path, sep="\t", header=False, index=False)

        return amplicon_path

    def _generate_amplicon_file_v2(self, amplicon_df: pd.DataFrame) -> Path:
        """
        Generate amplicon.txt file for CRISPResso.

        Format matches the original R script output:
        GeoID<tab>amplicon_sequence<tab>sgRNA_target<tab><tab>

        Args:
            amplicon_df: DataFrame with columns [geo_id, amplicon_seq, target]

        Returns:
            Path to the generated amplicon.txt file
        """
        amplicon_path = self.work_dir / "amplicon.txt"

        # Build output rows
        rows = []
        for _, row in amplicon_df.iterrows():
            rows.append({
                "GeoID": row["geo_id"],
                "seq": row["amplicon_seq"],
                "Target": row["target"],
                "i1": "",  # Empty columns required by CRISPResso
                "i2": "",
            })

        # Create DataFrame and save
        output_df = pd.DataFrame(rows)

        if output_df.empty:
            self._log("[WARNING] No amplicon rows to write")
            # Create empty file
            amplicon_path.touch()
            return amplicon_path

        # Save without header, tab-separated
        output_df.to_csv(amplicon_path, sep="\t", header=False, index=False)

        return amplicon_path

    def stage2_crispresso_pooled(self) -> bool:
        """
        Stage 2: Run CRISPRessoPooled.
        """
        self._log(">>> [Stage 2] Running CRISPRessoPooled (Docker)...")
        self._progress("crispr-mutation", 0)

        if not self.amplicon_file or not self.amplicon_file.exists():
            self._log("[ERROR] Amplicon file not found")
            return False

        result = self.crispresso.run_pooled(
            r1=self.config.r1,
            r2=self.config.r2,
            amplicon_file=self.amplicon_file,
            output_dir=self.work_dir,
            name="amp_aa",
        )

        self.pool_dir = self.work_dir / "CRISPRessoPooled_on_amp_aa"
        self._progress("crispr-mutation", 100)

        if result.success:
            self._log("    CRISPRessoPooled completed successfully")
            return True
        else:
            self._log(f"[WARNING] CRISPRessoPooled finished with code {result.return_code}")
            self._log(f"[WARNING] Log output: {result.log[-500:] if result.log else 'No log'}")
            
            # Even if CRISPRessoPooled fails, continue to next stages to attempt retries
            # and allow user to analyze any partial results
            return True

    def stage3_retry_missing(self) -> bool:
        """
        Stage 3: Retry failed samples.
        """
        self._log(">>> [Stage 3] Checking for missing samples...")
        self._progress("retry", 0)

        # If pool_dir doesn't exist, we can't perform retry
        if not self.pool_dir or not self.pool_dir.exists():
            self._log("[WARNING] Pool directory not found, skipping retry")
            return True

        if not self.amplicon_file:
            self._log("[WARNING] Amplicon file not found, skipping retry")
            return True

        results = self.crispresso.retry_missing_samples(
            amplicon_file=self.amplicon_file,
            pool_dir=self.pool_dir,
        )

        success_count = sum(1 for r in results.values() if r.success)
        self._log(f"    {success_count}/{len(results)} samples completed")
        self._progress("retry", 100)

        return True

    def stage4_collect_results(self) -> Path | None:
        """
        Stage 4: Collect results into final directory.
        """
        self._log(">>> [Stage 4] Collecting results...")
        self._progress("collect", 0)

        # If pool directory doesn't exist, we can't collect results
        if not self.pool_dir or not self.pool_dir.exists():
            self._log("[ERROR] Pool directory not found")
            self._log(f"[ERROR] Expected path: {self.pool_dir}")
            return None

        # Create results directory
        results_dir = self.work_dir / f"{self.config.project_name}_Results_Txt"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Find all CRISPResso output directories
        copied_count = 0
        for sample_dir in self.pool_dir.glob("CRISPResso_on_*"):
            if not sample_dir.is_dir():
                continue

            sample_name = sample_dir.name.replace("CRISPResso_on_", "")

            # Find allele frequency table
            freq_files = list(sample_dir.glob("*Alleles_frequency_table_around_sgRNA*txt"))
            if freq_files:
                src_file = freq_files[0]
                dst_file = results_dir / f"{sample_name}.txt"
                shutil.copy(src_file, dst_file)
                copied_count += 1

        self._log(f"    Collected {copied_count} result files")
        self._log(f"    Results saved to: {results_dir}")
        self._progress("collect", 100)

        return results_dir

    def stage5_collect_pngs(self) -> Path | None:
        """
        Stage 5: Collect PNG result images into final directory.

        Extracts *Alleles_frequency_table*.png from each CRISPResso_on_${geo_id}
        folder and saves as ${geo_id}.png in ${project_name}_Results_Png/
        """
        self._log(">>> [Stage 5] Collecting PNG images...")
        self._progress("collect_png", 0)

        # If pool directory doesn't exist, we can't collect results
        if not self.pool_dir or not self.pool_dir.exists():
            self._log("[WARNING] Pool directory not found, skipping PNG collection")
            return None

        # Create PNG results directory
        png_dir = self.work_dir / f"{self.config.project_name}_Results_Png"
        png_dir.mkdir(parents=True, exist_ok=True)

        # Find all CRISPResso output directories
        copied_count = 0
        for sample_dir in self.pool_dir.glob("CRISPResso_on_*"):
            if not sample_dir.is_dir():
                continue

            sample_name = sample_dir.name.replace("CRISPResso_on_", "")

            # Find allele frequency table PNG
            png_files = list(sample_dir.glob("*Alleles_frequency_table*.png"))
            if png_files:
                src_file = png_files[0]
                dst_file = png_dir / f"{sample_name}.png"
                shutil.copy(src_file, dst_file)
                copied_count += 1

        self._log(f"    Collected {copied_count} PNG files")
        self._log(f"    PNGs saved to: {png_dir}")
        self._progress("collect_png", 100)

        return png_dir

    def run(self) -> bool:
        """
        Run the complete pipeline.

        Returns:
            True if successful, False otherwise
        """
        self._log("=" * 60)
        self._log("CRISPResso Analysis Pipeline (Python)")
        self._log("=" * 60)
        self._log(f"Project: {self.config.project_name}")
        self._log(f"Output: {self.work_dir}")
        self._log("")

        # Validate inputs
        if not self.validate_inputs():
            return False

        # Stage 1: Preprocess
        if not self.stage1_preprocess():
            self._log("[FAILED] Stage 1: Preprocessing")
            return False

        # Stage 2: CRISPRessoPooled
        if not self.stage2_crispresso_pooled():
            self._log("[FAILED] Stage 2: CRISPRessoPooled")
            return False

        # Stage 3: Retry missing
        if not self.stage3_retry_missing():
            self._log("[WARNING] Stage 3: Some retries failed")
            # Continue anyway

        # Stage 4: Collect results (TXT)
        results_dir = self.stage4_collect_results()
        if not results_dir:
            self._log("[FAILED] Stage 4: Collect results")
            # Don't fail the pipeline completely if collection fails,
            # because the main analysis may still have succeeded
            # Return True to allow user to inspect what was created
            return True

        # Stage 5: Collect results (PNG)
        png_dir = self.stage5_collect_pngs()

        # Stage 6: Save results to local database (optional, default on)
        if self.config.save_to_db:
            self._log("")
            self._log(">>> [Stage 6] Saving results to local database...")
            try:
                import importlib
                import sys as _sys
                _scripts_dir = str(Path(__file__).resolve().parent.parent)
                if _scripts_dir not in _sys.path:
                    _sys.path.insert(0, _scripts_dir)
                save_mod = importlib.import_module("save_results")
                run_id = save_mod.save_pipeline_results(
                    project_name=self.config.project_name,
                    csv_path=self.config.csv,
                    r1_path=self.config.r1,
                    r2_path=self.config.r2,
                    work_dir=self.work_dir,
                    log_callback=self._log,
                )
                if run_id:
                    self._log(f"    Results saved (run_id={run_id})")
                else:
                    self._log("[WARNING] Failed to save results to database")
            except Exception as e:
                self._log(f"[WARNING] Save to database failed: {e}")
                # Don't fail the pipeline if save fails

        self._log("")
        self._log("=" * 60)
        self._log("Pipeline completed successfully!")
        self._log(f"Results (TXT): {results_dir}")
        if png_dir:
            self._log(f"Results (PNG): {png_dir}")
        self._log("=" * 60)

        return True


def run_pipeline(
    r1: Path,
    r2: Path,
    csv: Path,
    project_name: str,
    output_dir: Path,
    ref_genome: Path,
    ref_db: Path,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> bool:
    """
    Convenience function to run the pipeline.

    Args:
        r1: Path to R1 FASTQ file
        r2: Path to R2 FASTQ file
        csv: Path to input CSV file
        project_name: Name for this analysis project
        output_dir: Base output directory
        ref_genome: Path to reference genome (all.con)
        ref_db: Path to locus database (all.locus_brief_info.7.0)
        log_callback: Optional callback for log messages
        progress_callback: Optional callback for progress updates

    Returns:
        True if successful, False otherwise
    """
    config = PipelineConfig(
        r1=Path(r1),
        r2=Path(r2),
        csv=Path(csv),
        project_name=project_name,
        output_dir=Path(output_dir),
        ref_genome=Path(ref_genome),
        ref_db=Path(ref_db),
    )

    pipeline = Pipeline(
        config=config,
        log_callback=log_callback,
        progress_callback=progress_callback,
    )

    return pipeline.run()
