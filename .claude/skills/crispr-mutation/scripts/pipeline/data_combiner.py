"""
Data Combiner Module - Replaces combine.R

Combines data from multiple sources to generate the final amplicon file.
"""

from pathlib import Path

import pandas as pd


def combine_data(
    input_csv: pd.DataFrame,
    metadata: pd.DataFrame,
    coord_mapping: pd.DataFrame,
    sequences: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine data from multiple sources using cascading joins.

    Equivalent to the R script combine.R:
    1. Join input_csv with metadata on Target
    2. Join result with coord_mapping on pos
    3. Join result with sequences on pos_new

    Args:
        input_csv: User input DataFrame (GeoID, Locus, Target)
        metadata: Metadata from locus_filter (posss, Target)
        coord_mapping: Coordinate mapping (pos, pos_new)
        sequences: Sequence data (pos_new, seq)

    Returns:
        Combined DataFrame with all information
    """
    # Rename columns for clarity
    metadata_renamed = metadata.rename(columns={"posss": "pos"})

    # Step 1: Join input_csv with metadata on Target
    merged1 = input_csv.merge(metadata_renamed, on="Target", how="inner")

    # Step 2: Join with coord_mapping on pos
    merged2 = merged1.merge(coord_mapping, on="pos", how="inner")

    # Step 3: Join with sequences on pos_new
    merged3 = merged2.merge(sequences, on="pos_new", how="inner")

    return merged3


def generate_amplicon_file(
    combined_data: pd.DataFrame,
    output_path: Path,
) -> Path:
    """
    Generate the final amplicon.txt file for CRISPResso.

    Format: GeoID<tab>seq<tab>Target<tab>NA<tab>NA

    Args:
        combined_data: Combined DataFrame from combine_data()
        output_path: Path for output file

    Returns:
        Path to the generated file
    """
    # Select required columns
    result = combined_data[["GeoID", "seq", "Target"]].copy()

    # Add empty columns (i1, i2) as required by CRISPResso
    result["i1"] = ""
    result["i2"] = ""

    # Save without header for CRISPResso compatibility
    result.to_csv(output_path, sep="\t", header=False, index=False)

    return output_path


def combine_and_generate_amplicon(
    input_csv_path: Path,
    metadata: pd.DataFrame,
    sgrna_matches: pd.DataFrame,
    amplicon_sequences: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    """
    High-level function to combine all data and generate amplicon file.

    Args:
        input_csv_path: Path to user input CSV
        metadata: Metadata from locus_filter
        sgrna_matches: DataFrame with sgRNA match information
        amplicon_sequences: DataFrame with amplicon sequences
        output_dir: Directory for output files

    Returns:
        Tuple of (combine_path, amplicon_path)
    """
    # Read input CSV
    input_csv = pd.read_csv(
        input_csv_path, header=None, names=["GeoID", "Locus", "Target"]
    )

    # Handle header row if present
    if input_csv.iloc[0]["GeoID"] == "GeoID":
        input_csv = input_csv.iloc[1:].reset_index(drop=True)

    # Prepare coordinate mapping from sgRNA matches
    # Map from original position (pos) to new position (pos_new)
    coord_mapping = sgrna_matches[["pos", "pos_new"]].dropna()

    # Prepare sequences DataFrame
    # Map from pos_new to amplicon sequence
    sequences = amplicon_sequences[["pos_new", "amplicon_seq"]].rename(
        columns={"amplicon_seq": "seq"}
    )

    # Combine all data
    combined = combine_data(input_csv, metadata, coord_mapping, sequences)

    # Save combined data
    combine_path = output_dir / "combine.txt"
    combined.to_csv(combine_path, sep="\t", index=False)

    # Generate amplicon file
    amplicon_path = output_dir / "amplicon.txt"
    generate_amplicon_file(combined, amplicon_path)

    return combine_path, amplicon_path


def create_amplicon_from_matches(
    input_csv_path: Path,
    sgrna_matches: list,
    amplicon_sequences: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """
    Simplified function to create amplicon.txt directly from sgRNA matches.

    This is a more direct approach that bypasses some of the R script's
    intermediate steps.

    Args:
        input_csv_path: Path to user input CSV
        sgrna_matches: List of SgRNAMatch objects
        amplicon_sequences: DataFrame with pos, amplicon_seq, sg_seq columns
        output_dir: Directory for output files

    Returns:
        Path to the generated amplicon.txt
    """
    # Read input CSV
    input_csv = pd.read_csv(
        input_csv_path, header=None, names=["GeoID", "Locus", "Target"]
    )

    if input_csv.iloc[0]["GeoID"] == "GeoID":
        input_csv = input_csv.iloc[1:].reset_index(drop=True)

    # Build amplicon data
    amplicon_rows = []

    for match in sgrna_matches:
        if not match.found:
            continue

        # Find corresponding amplicon sequence
        amp_row = amplicon_sequences[amplicon_sequences["pos"] == match.pos]
        if amp_row.empty:
            continue

        seq = amp_row.iloc[0]["amplicon_seq"]
        sg_seq = match.sg_seq

        # Find GeoID from input_csv by matching Target
        # The Target in input_csv should match the original sgRNA
        # We need to handle reverse complement case
        geo_rows = input_csv[input_csv["Target"] == sg_seq]
        if geo_rows.empty:
            # Try with original target (before reverse complement)
            from Bio.Seq import Seq
            original_target = str(Seq(sg_seq).reverse_complement())
            geo_rows = input_csv[input_csv["Target"] == original_target]

        if geo_rows.empty:
            continue

        geo_id = geo_rows.iloc[0]["GeoID"]
        target = geo_rows.iloc[0]["Target"]

        amplicon_rows.append({
            "GeoID": geo_id,
            "seq": seq,
            "Target": target,
            "i1": "",
            "i2": "",
        })

    # Create DataFrame and save
    amplicon_df = pd.DataFrame(amplicon_rows)
    amplicon_path = output_dir / "amplicon.txt"
    amplicon_df.to_csv(amplicon_path, sep="\t", header=False, index=False)

    return amplicon_path
