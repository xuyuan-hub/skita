"""
Sequence Extractor Module - Replaces bedtools getfasta

Extracts sequences from a reference genome based on BED coordinates.
Uses pyfaidx for efficient indexed access to large FASTA files.
"""

from pathlib import Path
from typing import Iterator

import pandas as pd
from pyfaidx import Fasta


class SequenceExtractor:
    """
    Extract sequences from a reference genome using BED coordinates.

    Replaces the bedtools command:
        bedtools getfasta -fi ref.fa -bed coords.bed -fo output.fa
    """

    def __init__(self, ref_genome: Path):
        """
        Initialize the extractor with a reference genome.

        Args:
            ref_genome: Path to reference genome FASTA file.
                       Will automatically use .fai index if available.
        """
        self.ref_genome = ref_genome
        self._fasta: Fasta | None = None

    @property
    def fasta(self) -> Fasta:
        """Lazy-load the FASTA file."""
        if self._fasta is None:
            self._fasta = Fasta(str(self.ref_genome))
        return self._fasta

    def extract_sequence(self, chrom: str, start: int, stop: int) -> str:
        """
        Extract a single sequence from the reference genome.

        Args:
            chrom: Chromosome name (e.g., "Chr1")
            start: Start position (0-based)
            stop: End position (exclusive)

        Returns:
            DNA sequence string
        """
        return str(self.fasta[chrom][start:stop])

    def extract_from_bed(self, bed_df: pd.DataFrame) -> dict[str, str]:
        """
        Extract sequences for all regions in a BED DataFrame.

        Args:
            bed_df: DataFrame with columns ['chr', 'start', 'stop']

        Returns:
            Dictionary mapping region IDs (chr:start-stop) to sequences
        """
        sequences = {}
        for _, row in bed_df.iterrows():
            chrom = row["chr"]
            start = int(row["start"])
            stop = int(row["stop"])
            region_id = f"{chrom}:{start}-{stop}"
            sequences[region_id] = self.extract_sequence(chrom, start, stop)
        return sequences

    def extract_from_bed_iter(
        self, bed_df: pd.DataFrame
    ) -> Iterator[tuple[str, str]]:
        """
        Extract sequences as an iterator (memory efficient).

        Args:
            bed_df: DataFrame with columns ['chr', 'start', 'stop']

        Yields:
            Tuples of (region_id, sequence)
        """
        for _, row in bed_df.iterrows():
            chrom = row["chr"]
            start = int(row["start"])
            stop = int(row["stop"])
            region_id = f"{chrom}:{start}-{stop}"
            yield region_id, self.extract_sequence(chrom, start, stop)

    def close(self):
        """Close the FASTA file handle."""
        if self._fasta is not None:
            self._fasta.close()
            self._fasta = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def extract_sequences_to_fasta(
    ref_genome: Path,
    bed_df: pd.DataFrame,
    output_fasta: Path,
) -> Path:
    """
    Extract sequences and save to a FASTA file.

    Equivalent to: bedtools getfasta -fi ref.fa -bed coords.bed -fo output.fa

    Args:
        ref_genome: Path to reference genome FASTA
        bed_df: DataFrame with columns ['chr', 'start', 'stop']
        output_fasta: Path for output FASTA file

    Returns:
        Path to the output FASTA file
    """
    with SequenceExtractor(ref_genome) as extractor:
        with open(output_fasta, "w") as f:
            for region_id, sequence in extractor.extract_from_bed_iter(bed_df):
                f.write(f">{region_id}\n")
                f.write(f"{sequence}\n")

    return output_fasta


def extract_sequences_to_dict(
    ref_genome: Path,
    bed_df: pd.DataFrame,
) -> dict[str, str]:
    """
    Extract sequences and return as a dictionary.

    Args:
        ref_genome: Path to reference genome FASTA
        bed_df: DataFrame with columns ['chr', 'start', 'stop']

    Returns:
        Dictionary mapping region IDs to sequences
    """
    with SequenceExtractor(ref_genome) as extractor:
        return extractor.extract_from_bed(bed_df)
