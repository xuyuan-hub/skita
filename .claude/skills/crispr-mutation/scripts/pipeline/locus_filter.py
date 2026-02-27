"""
Locus Filter Module - Replaces 1-new.R

Filters locus information from the reference database based on user input CSV.
"""

from pathlib import Path
from dataclasses import dataclass

import pandas as pd


@dataclass
class FilterResult:
    """Result of locus filtering operation."""
    filtered_data: pd.DataFrame  # Full filtered dataset
    bed_data: pd.DataFrame       # BED format: chr, start, stop
    metadata: pd.DataFrame       # posss, Target mapping


def filter_locus(
    input_csv: Path,
    ref_db: Path,
) -> FilterResult:
    """
    Filter locus information from reference database.

    Equivalent to the R script 1-new.R:
    1. Read user CSV (GeoID, Locus, Target)
    2. Filter reference database by Locus
    3. Keep only representative transcripts (is_representative == "Y")
    4. Generate BED coordinates and metadata

    Args:
        input_csv: Path to user input CSV file (columns: GeoID/pid, Locus/locus, Target/target)
        ref_db: Path to reference database file (all.locus_brief_info.7.0)

    Returns:
        FilterResult containing filtered data, BED coordinates, and metadata
    """
    # Step 1: Read user input CSV
    # Handle both with and without header, and different header naming conventions
    user_data = pd.read_csv(input_csv, header=None, names=["GeoID", "Locus", "Target"])

    # If first row looks like header, skip it
    # Handle both uppercase (GeoID) and lowercase (pid) headers
    first_row_val = str(user_data.iloc[0]["GeoID"]).lower()
    if first_row_val in ("geoid", "pid", "id", "sample", "name"):
        user_data = user_data.iloc[1:].reset_index(drop=True)

    locus_ids = user_data["Locus"].unique().tolist()

    # Step 2: Read reference database
    ref_data = pd.read_csv(ref_db, sep="\t")

    # Step 3: Filter by Locus
    filtered = ref_data[ref_data["Locus"].isin(locus_ids)]

    # Step 4: Keep only representative transcripts
    representative = filtered[filtered["is_representative"] == "Y"].copy()

    # Step 5: Generate BED data (chr, start, stop)
    bed_data = representative[["chr", "start", "stop"]].copy()

    # Step 6: Generate metadata with position strings
    # Merge with user data to get Target information
    metadata = representative[["Locus", "chr", "start", "stop"]].merge(
        user_data, on="Locus", how="inner"
    )

    # Build position strings like in R script:
    # pos = chr:start
    # poss = chr:start-stop
    # posss = chr:start-stop_rowindex_Locus_GeoID
    metadata["pos"] = metadata["chr"] + ":" + metadata["start"].astype(str)
    metadata["poss"] = metadata["pos"] + "-" + metadata["stop"].astype(str)
    metadata["posss"] = (
        metadata["poss"] + "_" +
        metadata.index.astype(str) + "_" +
        metadata["Locus"] + "_" +
        metadata["GeoID"]
    )

    # Final metadata output: posss, Target
    metadata_output = metadata[["posss", "Target"]].copy()

    return FilterResult(
        filtered_data=representative,
        bed_data=bed_data,
        metadata=metadata_output,
    )


def save_filter_results(
    result: FilterResult,
    output_dir: Path,
    csv_name: str = "rfile1_1.csv",
    bed_name: str = "rfile1_2.bed",
    metadata_name: str = "rfile1_3.txt",
) -> tuple[Path, Path, Path]:
    """
    Save filter results to files.

    Args:
        result: FilterResult from filter_locus()
        output_dir: Directory to save files
        csv_name: Name for filtered CSV file
        bed_name: Name for BED file
        metadata_name: Name for metadata file

    Returns:
        Tuple of (csv_path, bed_path, metadata_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / csv_name
    bed_path = output_dir / bed_name
    metadata_path = output_dir / metadata_name

    # Save filtered data as CSV
    result.filtered_data.to_csv(csv_path, index=False)

    # Save BED file (no header, tab-separated)
    result.bed_data.to_csv(bed_path, sep="\t", header=False, index=False)

    # Save metadata (no header, tab-separated)
    result.metadata.to_csv(metadata_path, sep="\t", header=False, index=False)

    return csv_path, bed_path, metadata_path
