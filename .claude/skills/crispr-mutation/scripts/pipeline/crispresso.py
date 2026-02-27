"""
CRISPResso Docker Module

Encapsulates Docker calls to CRISPResso2 for CRISPR analysis.
"""

import subprocess
import shutil
import os
import platform
from pathlib import Path
from typing import Callable
from dataclasses import dataclass


@dataclass
class CRISPRessoResult:
    """Result of a CRISPResso run."""
    success: bool
    return_code: int
    output_dir: Path | None
    log: str


class CRISPRessoDocker:
    """
    Docker wrapper for CRISPResso2.

    Handles volume mounting, path translation, and command execution.
    """

    DEFAULT_IMAGE = "pinellolab/crispresso2:latest"

    # Default retry parameters for failed samples
    RETRY_PARAMS = (
        "--needleman_wunsch_gap_extend -2 "
        "--aln_seed_count 5 "
        "--plot_window_size 20 "
        "--max_rows_alleles_around_cut_to_plot 50 "
        "--prime_editing_pegRNA_extension_quantification_window_size 5 "
        "--quantification_window_size 1 "
        "--quantification_window_center -3 "
        "--conversion_nuc_from C "
        "--min_bp_quality_or_N 0 "
        "--default_min_aln_score 60 "
        "--needleman_wunsch_gap_incentive 1 "
        "--min_paired_end_reads_overlap 10 "
        "--needleman_wunsch_aln_matrix_loc EDNAFULL "
        "--prime_editing_pegRNA_scaffold_min_match_length 1 "
        "--aln_seed_min 2 "
        "--aln_seed_len 10 "
        "--needleman_wunsch_gap_open -20 "
        "--max_paired_end_reads_overlap 100 "
        "--conversion_nuc_to T "
        "--flexiguide_homology 80 "
        "--min_single_bp_quality 0 "
        "--exclude_bp_from_left 15 "
        "--min_average_read_quality 0 "
        "--min_frequency_alleles_around_cut_to_plot 0.2 "
        "--exclude_bp_from_right 15"
    )

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        log_callback: Callable[[str], None] | None = None,
    ):
        """
        Initialize CRISPResso Docker wrapper.

        Args:
            image: Docker image to use
            log_callback: Optional callback for log output
        """
        self.image = image
        self.log_callback = log_callback

    def _log(self, message: str):
        """Send message to log callback if available."""
        if self.log_callback:
            self.log_callback(message)

    def check_docker(self) -> bool:
        """Check if Docker is available."""
        return shutil.which("docker") is not None

    def pull_image(self) -> bool:
        """Pull the Docker image if not present."""
        try:
            # Check if image exists
            result = subprocess.run(
                ["docker", "image", "inspect", self.image],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self._log(f"Pulling Docker image: {self.image}")
                pull_result = subprocess.run(
                    ["docker", "pull", self.image],
                    capture_output=True,
                    text=True,
                )
                return pull_result.returncode == 0

            return True

        except Exception as e:
            self._log(f"Error checking/pulling Docker image: {e}")
            return False

    def run_pooled(
        self,
        r1: Path,
        r2: Path,
        amplicon_file: Path,
        output_dir: Path,
        name: str = "amp_aa",
    ) -> CRISPRessoResult:
        """
        Run CRISPRessoPooled analysis.

        Args:
            r1: Path to R1 FASTQ file
            r2: Path to R2 FASTQ file
            amplicon_file: Path to amplicon.txt file
            output_dir: Directory for output
            name: Pool name (default: amp_aa)

        Returns:
            CRISPRessoResult with run information
        """
        if not self.check_docker():
            return CRISPRessoResult(
                success=False,
                return_code=-1,
                output_dir=None,
                log="Docker is not available",
            )

        # Ensure image is available
        if not self.pull_image():
            return CRISPRessoResult(
                success=False,
                return_code=-1,
                output_dir=None,
                log="Failed to pull Docker image",
            )

        # Get absolute paths and convert to strings for Docker
        r1_abs = r1.resolve()
        r2_abs = r2.resolve()
        amplicon_abs = amplicon_file.resolve()
        output_abs = output_dir.resolve()

        # Input directory (for FASTQ files)
        input_dir = r1_abs.parent
        
        # Amplicon directory (separate from output to avoid path conflicts)
        amplicon_dir = amplicon_abs.parent

        # Convert Windows paths to proper format for Docker volume mounts
        # Docker on Windows needs paths like C:/path or //c/path
        output_str = str(output_abs).replace("\\", "/")
        input_str = str(input_dir).replace("\\", "/")
        amplicon_str = str(amplicon_dir).replace("\\", "/")

        self._log(f"Output path: {output_str}")
        self._log(f"Input path: {input_str}")
        self._log(f"Amplicon path: {amplicon_str}")

        # Build Docker command
        # Note: -w /data is required for CRISPResso2 to work properly
        # Mount amplicon file's directory separately to /amplicon to avoid path conflicts
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{output_str}:/data",
            "-v", f"{input_str}:/input:ro",
            "-v", f"{amplicon_str}:/amplicon:ro",
            "-w", "/data",
            self.image,
            "CRISPRessoPooled",
            "-r1", f"/input/{r1_abs.name}",
            "-r2", f"/input/{r2_abs.name}",
            "-f", f"/amplicon/{amplicon_abs.name}",
            "--name", name,
            "-p", "max",
            "--output_folder", "/data",
        ]

        self._log(f"Running CRISPRessoPooled: {name}")
        self._log(f"Command: {' '.join(cmd)}")

        try:
            # Prepare environment - ALWAYS set MSYS variables to fix Windows path conversion
            env = os.environ.copy()
            # Fix Windows MSYS/Git Bash path conversion issue
            env["MSYS_NO_PATHCONV"] = "1"
            env["MSYS2_ARG_CONV_EXCL"] = "*"

            # Run Docker command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            log_lines = []
            for line in process.stdout:
                log_lines.append(line)
                self._log(line.rstrip())

            process.wait()

            pool_output_dir = output_abs / f"CRISPRessoPooled_on_{name}"

            return CRISPRessoResult(
                success=process.returncode == 0,
                return_code=process.returncode,
                output_dir=pool_output_dir if pool_output_dir.exists() else None,
                log="".join(log_lines),
            )

        except Exception as e:
            return CRISPRessoResult(
                success=False,
                return_code=-1,
                output_dir=None,
                log=f"Error running CRISPRessoPooled: {e}",
            )

    def run_single(
        self,
        r1: Path,
        amplicon_seq: str,
        guide_seq: str,
        output_dir: Path,
        name: str,
        extra_params: str = "",
    ) -> CRISPRessoResult:
        """
        Run single-sample CRISPResso analysis.

        Used for retry/补跑 of failed samples.

        Args:
            r1: Path to demultiplexed FASTQ file
            amplicon_seq: Amplicon sequence
            guide_seq: Guide RNA sequence
            output_dir: Directory for output
            name: Sample name
            extra_params: Additional CRISPResso parameters

        Returns:
            CRISPRessoResult with run information
        """
        if not self.check_docker():
            return CRISPRessoResult(
                success=False,
                return_code=-1,
                output_dir=None,
                log="Docker is not available",
            )

        r1_abs = r1.resolve()
        output_abs = output_dir.resolve()

        # Use parent directory for volume mount
        work_dir = r1_abs.parent.parent  # Go up from CRISPRessoPooled_on_xxx

        # Relative path within the mounted volume
        r1_rel = r1_abs.relative_to(work_dir)

        # Convert Windows paths to proper format for Docker
        work_str = str(work_dir).replace("\\", "/")

        # Build command
        params = extra_params if extra_params else self.RETRY_PARAMS

        cmd = [
            "docker", "run", "--rm",
            "-v", f"{work_str}:/data",
            self.image,
            "CRISPResso",
            "-r1", f"/data/{r1_rel.as_posix()}",
            "-a", amplicon_seq,
            "-g", guide_seq,
            "-o", f"/data/{output_abs.relative_to(work_dir).as_posix()}",
            "--name", name,
        ] + params.split()

        self._log(f"Running CRISPResso retry: {name}")

        try:
            # Prepare environment - ALWAYS set MSYS variables to fix Windows path conversion
            env = os.environ.copy()
            env["MSYS_NO_PATHCONV"] = "1"
            env["MSYS2_ARG_CONV_EXCL"] = "*"

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            log_lines = []
            for line in process.stdout:
                log_lines.append(line)
                self._log(line.rstrip())

            process.wait()

            sample_output_dir = output_abs / f"CRISPResso_on_{name}"

            return CRISPRessoResult(
                success=process.returncode == 0,
                return_code=process.returncode,
                output_dir=sample_output_dir if sample_output_dir.exists() else None,
                log="".join(log_lines),
            )

        except Exception as e:
            return CRISPRessoResult(
                success=False,
                return_code=-1,
                output_dir=None,
                log=f"Error running CRISPResso: {e}",
            )

    def retry_missing_samples(
        self,
        amplicon_file: Path,
        pool_dir: Path,
    ) -> dict[str, CRISPRessoResult]:
        """
        Retry analysis for samples that failed in pooled run.

        Args:
            amplicon_file: Path to amplicon.txt
            pool_dir: CRISPRessoPooled output directory

        Returns:
            Dictionary mapping sample names to results
        """
        results = {}

        # Read amplicon file to get sample info
        with open(amplicon_file) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue

                sample_id = parts[0]
                amplicon_seq = parts[1]
                guide_seq = parts[2]

                # Check if result exists
                expected_file = (
                    pool_dir /
                    f"CRISPResso_on_{sample_id}" /
                    "CRISPResso_quantification_of_editing_frequency.txt"
                )

                if expected_file.exists():
                    self._log(f"[OK] {sample_id}")
                    results[sample_id] = CRISPRessoResult(
                        success=True,
                        return_code=0,
                        output_dir=expected_file.parent,
                        log="Already completed",
                    )
                else:
                    self._log(f"[MISSING] {sample_id} - retrying...")

                    # Find demultiplexed FASTQ
                    demux_r1 = pool_dir / f"AMPL_{sample_id}.fastq.gz"

                    if demux_r1.exists():
                        result = self.run_single(
                            r1=demux_r1,
                            amplicon_seq=amplicon_seq,
                            guide_seq=guide_seq,
                            output_dir=pool_dir,
                            name=sample_id,
                        )
                        results[sample_id] = result
                    else:
                        self._log(f"  Demux file not found: {demux_r1}")
                        results[sample_id] = CRISPRessoResult(
                            success=False,
                            return_code=-1,
                            output_dir=None,
                            log=f"Demux file not found: {demux_r1}",
                        )

        return results
