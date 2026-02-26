"""
sgRNA Locator Module - Refactored from extract_fasta.py

Locates sgRNA sequences within extracted genomic sequences.
Finds both forward and reverse complement matches.
"""

import re
from pathlib import Path
from dataclasses import dataclass

import pandas as pd
from Bio.Seq import Seq


@dataclass
class SgRNAMatch:
    """Result of sgRNA matching for a single position."""
    pos: str           # Original position identifier (posss format)
    found: bool        # Whether sgRNA was found
    direction: str     # "forward", "reverse", or "not_found"
    sg_seq: str        # The sgRNA sequence (or reverse complement)
    sg_pos: int | None # Position in the sequence (1-based)
    upstream_coord: str   # Upstream 150bp coordinate (e.g., "Chr1:850-1000")
    downstream_coord: str # Downstream 150bp coordinate
    amplicon_coord: str   # Full amplicon coordinate (upstream_start to downstream_end)
    geo_id: str        # GeoID extracted from posss
    target: str        # Original Target sequence from input


def find_sgrna_position(sg: str, sequence: str) -> int | None:
    """
    Find the position of sgRNA in a sequence.

    Args:
        sg: sgRNA sequence to search for
        sequence: DNA sequence to search in

    Returns:
        1-based position if found, None otherwise
    """
    match = re.search(sg, sequence)
    if match:
        return match.start() + 1  # Convert to 1-based
    return None


def locate_sgrna(
    sequences: dict[str, str],
    metadata: pd.DataFrame,
    seq_length: int = 150,
) -> list[SgRNAMatch]:
    """
    Locate sgRNA sequences in extracted genomic sequences.

    Searches for both forward and reverse complement of the sgRNA.
    Calculates upstream and downstream coordinates for amplicon design.

    Following the original bash script logic:
    - abs_pos = start_pos + sgRNA_position - 1 (where sgRNA is found in sequence)
    - upstream: abs_pos - seq_length to abs_pos
    - bbs_pos = start_pos + sgRNA_position + 23 (downstream starts after PAM)
    - downstream: bbs_pos to bbs_pos + seq_length
    - amplicon: (abs_pos - seq_length) to (bbs_pos + seq_length)

    Args:
        sequences: Dictionary mapping region IDs (chr:start-stop) to sequences
        metadata: DataFrame with columns ['posss', 'Target']
                  where posss is like "Chr1:1000-1100_1_Locus_GeoID"
        seq_length: Length of flanking regions (default 150bp)

    Returns:
        List of SgRNAMatch results
    """
    results = []

    for _, row in metadata.iterrows():
        posss = row["posss"]
        target = row["Target"]

        # Parse position from posss: "Chr1:1000-1100_1_Locus_GeoID"
        # Format: chr:start-stop_index_Locus_GeoID
        pos_parts = posss.split("_")
        base_pos = pos_parts[0]  # "Chr1:1000-1100"

        # Extract GeoID (last part)
        geo_id = pos_parts[-1] if len(pos_parts) >= 4 else ""

        # Skip if no sequence for this position
        if base_pos not in sequences:
            results.append(SgRNAMatch(
                pos=posss,
                found=False,
                direction="not_found",
                sg_seq=target,
                sg_pos=None,
                upstream_coord="",
                downstream_coord="",
                amplicon_coord="",
                geo_id=geo_id,
                target=target,
            ))
            continue

        sequence = sequences[base_pos]

        # Parse coordinates from base_pos
        # Pattern: Chr1:1000-1100 or Chr01:1000-1100
        coord_match = re.match(r"(Chr\d+):(\d+)-(\d+)", base_pos)
        if not coord_match:
            results.append(SgRNAMatch(
                pos=posss,
                found=False,
                direction="not_found",
                sg_seq=target,
                sg_pos=None,
                upstream_coord="",
                downstream_coord="",
                amplicon_coord="",
                geo_id=geo_id,
                target=target,
            ))
            continue

        chrom = coord_match.group(1)
        start_pos = int(coord_match.group(2))

        # Search for forward sgRNA
        forward_pos = find_sgrna_position(target, sequence)

        # Search for reverse complement
        sg_reverse = str(Seq(target).reverse_complement())
        reverse_pos = find_sgrna_position(sg_reverse, sequence)

        if forward_pos is not None:
            # Forward match found
            # Following extract_fasta.py logic:
            # abs_pos = start_pos + result - 1
            # bbs_pos = start_pos + result + 23
            abs_pos = start_pos + forward_pos - 1
            bbs_pos = start_pos + forward_pos + 23

            # Upstream: from (abs_pos - seq_length) to abs_pos
            upstream_start = abs_pos - seq_length
            upstream_end = abs_pos

            # Downstream: from bbs_pos to (bbs_pos + seq_length)
            downstream_start = bbs_pos
            downstream_end = bbs_pos + seq_length

            # Amplicon: full region from upstream_start to downstream_end
            amplicon_start = upstream_start
            amplicon_end = downstream_end

            results.append(SgRNAMatch(
                pos=posss,
                found=True,
                direction="forward",
                sg_seq=target,
                sg_pos=forward_pos,
                upstream_coord=f"{chrom}:{upstream_start}-{upstream_end}",
                downstream_coord=f"{chrom}:{downstream_start}-{downstream_end}",
                amplicon_coord=f"{chrom}:{amplicon_start}-{amplicon_end}",
                geo_id=geo_id,
                target=target,
            ))

        elif reverse_pos is not None:
            # Reverse complement match found - same coordinate calculation
            abs_pos = start_pos + reverse_pos - 1
            bbs_pos = start_pos + reverse_pos + 23

            upstream_start = abs_pos - seq_length
            upstream_end = abs_pos
            downstream_start = bbs_pos
            downstream_end = bbs_pos + seq_length
            amplicon_start = upstream_start
            amplicon_end = downstream_end

            results.append(SgRNAMatch(
                pos=posss,
                found=True,
                direction="reverse",
                sg_seq=sg_reverse,  # Use the reverse complement for matching
                sg_pos=reverse_pos,
                upstream_coord=f"{chrom}:{upstream_start}-{upstream_end}",
                downstream_coord=f"{chrom}:{downstream_start}-{downstream_end}",
                amplicon_coord=f"{chrom}:{amplicon_start}-{amplicon_end}",
                geo_id=geo_id,
                target=target,  # Keep original target for CRISPResso
            ))

        else:
            # No match found
            results.append(SgRNAMatch(
                pos=posss,
                found=False,
                direction="not_found",
                sg_seq=target,
                sg_pos=None,
                upstream_coord="",
                downstream_coord="",
                amplicon_coord="",
                geo_id=geo_id,
                target=target,
            ))

    return results


def matches_to_dataframe(matches: list[SgRNAMatch]) -> pd.DataFrame:
    """
    Convert list of SgRNAMatch to DataFrame.

    Args:
        matches: List of SgRNAMatch objects

    Returns:
        DataFrame with all match information
    """
    data = [
        {
            "pos": m.pos,
            "found": m.found,
            "direction": m.direction,
            "sg_seq": m.sg_seq,
            "sg_pos": m.sg_pos,
            "upstream_coord": m.upstream_coord,
            "downstream_coord": m.downstream_coord,
            "amplicon_coord": m.amplicon_coord,
            "geo_id": m.geo_id,
            "target": m.target,
        }
        for m in matches
    ]
    return pd.DataFrame(data)


def get_sgrna_bed_coordinates(matches: list[SgRNAMatch]) -> pd.DataFrame:
    """
    Extract BED coordinates from sgRNA matches for sequence extraction.

    Returns coordinates for the sgRNA flanking regions (upstream + downstream)
    and the full amplicon region.

    Args:
        matches: List of SgRNAMatch objects

    Returns:
        DataFrame with BED coordinates (chr, start, stop)
    """
    bed_rows = []

    for match in matches:
        if not match.found:
            continue

        # Parse upstream coordinate
        if match.upstream_coord:
            upstream_match = re.match(
                r"(Chr\d+):(\d+)-(\d+)", match.upstream_coord
            )
            if upstream_match:
                bed_rows.append({
                    "chr": upstream_match.group(1),
                    "start": int(upstream_match.group(2)),
                    "stop": int(upstream_match.group(3)),
                    "pos": match.pos,
                    "type": "upstream",
                })

        # Parse downstream coordinate
        if match.downstream_coord:
            downstream_match = re.match(
                r"(Chr\d+):(\d+)-(\d+)", match.downstream_coord
            )
            if downstream_match:
                bed_rows.append({
                    "chr": downstream_match.group(1),
                    "start": int(downstream_match.group(2)),
                    "stop": int(downstream_match.group(3)),
                    "pos": match.pos,
                    "type": "downstream",
                })

        # Parse amplicon coordinate (full region)
        if match.amplicon_coord:
            amplicon_match = re.match(
                r"(Chr\d+):(\d+)-(\d+)", match.amplicon_coord
            )
            if amplicon_match:
                bed_rows.append({
                    "chr": amplicon_match.group(1),
                    "start": int(amplicon_match.group(2)),
                    "stop": int(amplicon_match.group(3)),
                    "pos": match.pos,
                    "type": "amplicon",
                })

    return pd.DataFrame(bed_rows)


def get_amplicon_bed_coordinates(matches: list[SgRNAMatch]) -> pd.DataFrame:
    """
    Extract only amplicon BED coordinates from sgRNA matches.

    Args:
        matches: List of SgRNAMatch objects

    Returns:
        DataFrame with BED coordinates for amplicons (chr, start, stop, geo_id)
    """
    bed_rows = []

    for match in matches:
        if not match.found or not match.amplicon_coord:
            continue

        amplicon_match = re.match(
            r"(Chr\d+):(\d+)-(\d+)", match.amplicon_coord
        )
        if amplicon_match:
            bed_rows.append({
                "chr": amplicon_match.group(1),
                "start": int(amplicon_match.group(2)),
                "stop": int(amplicon_match.group(3)),
                "pos": match.pos,
                "geo_id": match.geo_id,
                "target": match.target,
            })

    return pd.DataFrame(bed_rows)


def build_amplicon_sequences(
    matches: list[SgRNAMatch],
    upstream_seqs: dict[str, str],
    downstream_seqs: dict[str, str],
) -> pd.DataFrame:
    """
    Build full amplicon sequences by combining upstream and downstream regions.

    DEPRECATED: Use build_amplicon_from_direct_extraction instead.

    Args:
        matches: List of SgRNAMatch objects
        upstream_seqs: Dictionary mapping upstream coordinates to sequences
        downstream_seqs: Dictionary mapping downstream coordinates to sequences

    Returns:
        DataFrame with columns [pos, amplicon_seq, pos_new]
    """
    amplicon_data = []

    for match in matches:
        if not match.found:
            continue

        # Get upstream sequence
        upstream_key = match.upstream_coord
        upstream_seq = upstream_seqs.get(upstream_key, "")

        # Get downstream sequence
        downstream_key = match.downstream_coord
        downstream_seq = downstream_seqs.get(downstream_key, "")

        # Combine to form amplicon
        # amplicon = upstream + sgRNA+PAM (23bp) + downstream
        amplicon_seq = upstream_seq + match.sg_seq + downstream_seq

        # Create position mapping
        pos_new = match.upstream_coord  # Use upstream coord as new position key

        amplicon_data.append({
            "pos": match.pos,
            "amplicon_seq": amplicon_seq,
            "pos_new": pos_new,
            "sg_seq": match.sg_seq,
        })

    return pd.DataFrame(amplicon_data)


def build_amplicon_from_direct_extraction(
    matches: list[SgRNAMatch],
    amplicon_seqs: dict[str, str],
) -> pd.DataFrame:
    """
    Build amplicon data using directly extracted sequences from reference genome.

    This is the correct approach matching the original bash script:
    1. Extract the full amplicon region (upstream_start to downstream_end)
    2. Use this extracted sequence directly

    Args:
        matches: List of SgRNAMatch objects
        amplicon_seqs: Dictionary mapping amplicon coordinates to sequences
                       Keys are in format "Chr1:12345-12698"

    Returns:
        DataFrame with columns [geo_id, amplicon_seq, target] ready for amplicon.txt
    """
    amplicon_data = []

    for match in matches:
        if not match.found or not match.amplicon_coord:
            continue

        # Get amplicon sequence using the coordinate as key
        amplicon_seq = amplicon_seqs.get(match.amplicon_coord, "")

        if not amplicon_seq:
            continue

        amplicon_data.append({
            "geo_id": match.geo_id,
            "amplicon_seq": amplicon_seq,
            "target": match.target,
            "pos": match.pos,
            "amplicon_coord": match.amplicon_coord,
        })

    return pd.DataFrame(amplicon_data)
