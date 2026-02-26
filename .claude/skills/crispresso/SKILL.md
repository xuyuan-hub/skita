---
name: crispresso
description: Run CRISPResso2 CRISPR/Cas9 mutation analysis pipeline. Use when user wants to analyze CRISPR editing results, process FASTQ files for mutation detection, or run batch CRISPResso analysis on multiple samples. Handles Excel/CSV sample lists, FASTQ data preparation, amplicon generation, Docker-based CRISPRessoPooled execution, and result collection.
---

# CRISPResso Analysis Pipeline

Automated CRISPR/Cas9 mutation analysis using CRISPRessoPooled.

Included:
- `scripts/pipeline/` - Complete analysis pipeline modules
- `scripts/` - Batch processing, result collection, mutation analysis scripts
- `genomes/` - Reference genome (`all.con`) and locus database (`all.locus_brief_info.7.0`)

Scripts auto-detect their own `genomes/` directory as default reference path.

## Prerequisites

- Docker running with `pinellolab/crispresso2:latest` image
- Python 3.13+ with dependencies: `pip install pandas biopython pyfaidx openpyxl`

## Scripts Overview

### Pipeline Core Modules (`scripts/pipeline/`)

| Module | Description |
|--------|-------------|
| `runner.py` | Main pipeline controller, orchestrates all 5 stages via `Pipeline` class and `PipelineConfig` dataclass |
| `locus_filter.py` | Filters locus information from reference database (replaces R script `1-new.R`) |
| `sequence_extractor.py` | Extracts sequences from reference genome using pyfaidx (replaces `bedtools getfasta`) |
| `sgrna_locator.py` | Locates sgRNA sequences (forward + reverse complement) and calculates amplicon coordinates |
| `crispresso.py` | Docker wrapper for CRISPResso2, handles volume mounting, path translation, pooled/single runs |
| `data_combiner.py` | Combines data from multiple sources to generate amplicon file (replaces `combine.R`) |

### Utility Scripts (`scripts/`)

| Script | Description |
|--------|-------------|
| `batch_run.py` | CLI for batch processing multiple samples with `--data-dir`, `--samples`, `--all` options |
| `collect_results.py` | Collects TXT/PNG result files from existing CRISPRessoPooled runs |
| `mutation_define_NGS.py` | Analyzes mutation types from allele frequency tables, generates mutation summary TSV |

## Data Preparation

### Convert Excel to CSV

If input is Excel (.xlsx), convert to CSV format:

```python
import pandas as pd
df = pd.read_excel('path/to/file.xlsx')
df.columns = ['GeoID', 'Locus', 'Target']  # Ensure correct column names
df.to_csv('path/to/samples.csv', index=False)
```

Required CSV columns:
- `GeoID`: Sample unique identifier
- `Locus`: Gene locus ID (e.g., LOC_Os01g01010)
- `Target`: sgRNA sequence with PAM (23bp, e.g., ATCGATCGATCGATCGATCGNGG)

### Data Directory Structure

```
data_dir/
├── samples.csv           # Sample information
└── data/
    └── 2_HQData/         # High-quality FASTQ files
        ├── SAMPLE1_HQ_R1.fq.gz
        ├── SAMPLE1_HQ_R2.fq.gz
        └── ...
```

## Running Analysis

### Single Sample

```python
import sys
from pathlib import Path

# Add skill scripts to path
sys.path.insert(0, str(Path('.claude/skills/crispresso/scripts').resolve()))

from pipeline.runner import Pipeline, PipelineConfig

config = PipelineConfig(
    r1=Path('data/sample/R1.fq.gz'),
    r2=Path('data/sample/R2.fq.gz'),
    csv=Path('data/samples.csv'),
    project_name='SampleName',
    output_dir=Path('data/result'),
    ref_genome=Path('genomes/all.con'),
    ref_db=Path('genomes/all.locus_brief_info.7.0'),
)

pipeline = Pipeline(config=config, log_callback=print)
success = pipeline.run()
```

### Batch Processing

Use the batch script for multiple samples (self-contained, works from any project root):

```bash
# Process specific samples
python .claude/skills/crispresso/scripts/batch_run.py --data-dir data/26_01_28 --samples SA_30,SB_19

# Process all samples in directory
python .claude/skills/crispresso/scripts/batch_run.py --data-dir data/26_01_28 --all
```

### Manual Docker Execution (Windows)

On Windows, set `MSYS_NO_PATHCONV=1` to prevent path conversion issues:

```bash
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "C:\path\to\output:/DATA" \
  -v "C:\path\to\fastq:/INPUT:ro" \
  pinellolab/crispresso2:latest \
  CRISPRessoPooled \
  -r1 /INPUT/sample_R1.fq.gz \
  -r2 /INPUT/sample_R2.fq.gz \
  -f /DATA/amplicon.txt \
  --name amp_aa -p max --output_folder /DATA
```

## Pipeline Stages

1. **Preprocess** (`locus_filter.py` → `sequence_extractor.py` → `sgrna_locator.py`)
   - Filter loci from reference DB by Locus ID, keep representative transcripts
   - Extract genomic sequences using pyfaidx (BED coordinates)
   - Locate sgRNA (forward + reverse complement), calculate amplicon coordinates
   - Generate `amplicon.txt` for CRISPResso

2. **CRISPRessoPooled** (`crispresso.py`)
   - Docker volume mounts: output→`/data`, FASTQ→`/input:ro`, amplicon→`/amplicon:ro`
   - Sets `MSYS_NO_PATHCONV=1` for Windows compatibility

3. **Retry** - Re-run failed samples individually using demultiplexed FASTQ

4. **Collect TXT** - Gather `*Alleles_frequency_table_around_sgRNA*.txt` to `*_Results_Txt/`

5. **Collect PNG** - Gather `*Alleles_frequency_table*.png` to `*_Results_Png/`

6. **Mutation Interpretation** (`mutation_define_NGS.py`)
   - Analyze indels: deletion/insertion classification
   - Zygosity detection based on allele count and read thresholds

7. **Save Results** (`save_results.py`，默认开启，可通过 `save_to_db=False` 关闭）
   - 将 CSV、mutation.tsv、TXT、PNG 文件存入 `data/files/crispresso/`（通过 `scripts/files.py`）
   - 运行记录存入 `data_crispresso_run` 表（项目名、样本数、成功/失败数、日期）
   - 样本结果存入 `data_crispresso_sample` 表（sample_id、locus、target、突变解读、文件路径）
   - Schema 定义：`meta/crispresso_run.json`、`meta/crispresso_sample.json`

## Key Data Flow

```
CSV (GeoID, Locus, Target) + FASTQ (R1, R2)
    ↓ locus_filter.py
Filter by Locus → BED coordinates + metadata (posss format)
    ↓ sequence_extractor.py
Extract genomic sequences via pyfaidx
    ↓ sgrna_locator.py
Locate sgRNA → amplicon coordinates (±150bp flanking)
    ↓ runner.py
Generate amplicon.txt (GeoID<tab>seq<tab>Target<tab><tab>)
    ↓ crispresso.py
CRISPRessoPooled (Docker) → CRISPRessoPooled_on_amp_aa/
    ↓ runner.py / collect_results.py
Collect *_Results_Txt/*.txt + *_Results_Png/*.png
    ↓ mutation_define_NGS.py
Mutation interpretation → *_mutation.tsv
```

## Coordinate System

```
posss format: Chr1:start-stop_index_Locus_GeoID

sgRNA coordinate calculation:
  abs_pos = start_pos + sgRNA_position_in_seq - 1
  bbs_pos = start_pos + sgRNA_position_in_seq + 23
  upstream:   Chr:abs_pos-150  to  abs_pos
  downstream: bbs_pos  to  bbs_pos+150
  amplicon:   abs_pos-150  to  bbs_pos+150
```

## Output

Results in `<output_dir>/<project_name>/`:
- `amplicon.txt`: Amplicon sequences for CRISPResso input
- `CRISPRessoPooled_on_amp_aa/`: Raw CRISPResso output
- `<project_name>_Results_Txt/`: One `.txt` file per sample with allele frequencies
- `<project_name>_Results_Png/`: One `.png` file per sample with allele frequency visualization
- `<project_name>_mutation.tsv`: Mutation interpretation summary

## Collecting Results from Existing Analysis

```bash
# Collect PNG files
python .claude/skills/crispresso/scripts/collect_results.py output/SA --png

# Collect TXT files
python .claude/skills/crispresso/scripts/collect_results.py output/SA --txt

# Collect both
python .claude/skills/crispresso/scripts/collect_results.py output/SA --all
```

## Mutation Interpretation

After collecting TXT results:

```bash
python .claude/skills/crispresso/scripts/mutation_define_NGS.py --path output/SA/SA_Results_Txt
```

Outputs `<project>_mutation.tsv` with classifications:

| Interpretation | Description |
|----------------|-------------|
| 无突变 | No frameshift mutation detected |
| 有突变 | Mutation detected (unspecified zygosity) |
| 纯合突变 | Homozygous mutation (single allele, reads >= 200) |
| 杂合突变 | Heterozygous mutation (WT + mutant, both reads >= 200) |
| 双等位突变 | Biallelic mutation (two different mutations, both reads >= 200) |

**Mutation type notation:**
- `X缺失` / `XX缺失`: 1-2bp deletion with specific bases
- `Nbp缺失`: >=3bp deletion
- `X插入` / `XX插入`: 1-2bp insertion with specific bases
- `Nbp插入`: >=3bp insertion
- `片段缺失/插入`: Large indel at amplicon boundary
- `WT`: Wild-type sequence

**Rules:** Minimum 200 reads for confident zygosity calls; 10%/20% frequency thresholds for allele inclusion.

## Troubleshooting

### Docker 未安装

如果提示 `docker: command not found` 或无法连接 Docker daemon：

1. **安装 Docker Desktop**: https://www.docker.com/products/docker-desktop/
2. 安装后启动 Docker Desktop，等待状态变为 "Running"
3. 验证安装: `docker --version`

### CRISPResso2 镜像不存在

如果提示 `Unable to find image 'pinellolab/crispresso2:latest'`：

```bash
# 方式1: 从 Docker Hub 拉取（需要网络）
docker pull pinellolab/crispresso2:latest

# 方式2: 联系 2827883762@qq.com 获取离线镜像文件，然后加载
docker load -i crispresso2_latest.tar
```

### 参考基因组文件缺失

`genomes/` 目录下的参考基因组文件（`all.con` 和 `all.locus_brief_info.7.0`）为大文件，不包含在 Git 仓库中。

获取方式：
- 联系 **2827883762@qq.com** 获取参考基因组文件
- 将 `all.con` 和 `all.locus_brief_info.7.0` 放入 `.claude/skills/crispresso/genomes/` 目录

### Docker 未启动

如果提示 `error during connect` 或 `Cannot connect to the Docker daemon`：

- **Windows**: 打开 Docker Desktop 应用，等待左下角状态变为绿色 "Running"
- **Linux**: `sudo systemctl start docker`
- **macOS**: 从应用程序中启动 Docker Desktop

### Docker Path Issues (Windows)

如果 CRISPResso 输出路径显示为 `E:/Git/data/...`，确保设置了 `MSYS_NO_PATHCONV=1`。
Pipeline 脚本已自动处理此问题。

### Guide Not Found in Amplicon

如果出现 "guide sequence not present in amplicon" 错误，检查 `sgrna_locator.py` 中 amplicon 构建是否包含 sgRNA：
```python
amplicon_seq = upstream_seq + match.sg_seq + downstream_seq
```

## 环境自检与测试

当需要验证 CRISPResso pipeline 能否正常运行时，按以下步骤执行自检。

### 第一步：环境检查

逐项验证依赖是否就绪：

```bash
# 1. Python 依赖
python -c "import pandas; import Bio; import pyfaidx; import openpyxl; print('All dependencies OK')"

# 2. Docker 和 CRISPResso2 镜像
docker --version
docker image inspect pinellolab/crispresso2:latest --format '{{.Id}}'

# 3. 参考基因组文件
ls .claude/skills/crispresso/genomes/all.con
ls .claude/skills/crispresso/genomes/all.locus_brief_info.7.0

# 4. 测试数据
ls .claude/skills/crispresso/tests/data/GOA_8/GOA_8.csv
ls .claude/skills/crispresso/tests/data/GOA_8/GOA_8_HQ_R1.fq.gz
ls .claude/skills/crispresso/tests/data/GOA_8/GOA_8_HQ_R2.fq.gz
```

所有命令都应正常输出，无报错。如果缺少文件，参考下方 Troubleshooting 章节。

### 第二步：运行测试

测试脚本位于 `tests/test_pipeline.py`，包含 3 组共 16 个测试用例：

```bash
# 仅测试预处理阶段（不需要 Docker，约 1 秒）
python -m pytest .claude/skills/crispresso/tests/test_pipeline.py -k "preprocess" -v

# 完整测试（需要 Docker + CRISPResso2 镜像 + FASTQ 数据，约 9 分钟）
python -m pytest .claude/skills/crispresso/tests/test_pipeline.py -v

# 仅测试突变分析（需要 GOA_8_Results_Txt/ 预期结果文件）
python -m pytest .claude/skills/crispresso/tests/test_pipeline.py -k "mutation" -v
```

### 第三步：核对结果

| 测试组 | 测试项 | 预期 |
|--------|--------|------|
| **TestPreprocess** (5项，无需Docker) | preprocess_succeeds | PASSED |
| | sgrna_all_found (56/56) | PASSED |
| | amplicon_file_created (56行) | PASSED |
| | amplicon_format (5列 tab 分隔，target 23bp) | PASSED |
| | locus_filter_count (56 loci) | PASSED |
| **TestFullPipeline** (4项，需Docker) | pipeline_succeeds | PASSED |
| | result_txt_count = 50 | PASSED |
| | result_png_count = 50 | PASSED |
| | missing_samples = BG8823-8, BG8837-8, BG9281-8, BG9417-8, BG9459-8, BG9477-8 | PASSED |
| **TestMutationInterpretation** (7项) | describe_sequence_variation_wt / deletion / insertion | PASSED |
| | mutation_results_exist (优先用预存数据，回退到 pipeline 输出) | PASSED |
| | mutation_output_file (50行 TSV) | PASSED |
| | mutation_no_mutation_count = 6 | PASSED |
| | mutation_specific_results (双等位: BG8832-8, BG9390-8, BG9391-8; 杂合: BG9358-8) | PASSED |

**正常结果**: 16 passed（约 10 分钟）。突变分析测试会自动使用 full pipeline 的输出，无需预先准备 `GOA_8_Results_Txt/`。任何 FAILED 均表示环境或代码有问题，需排查。

### 测试数据

测试数据位于 `tests/data/GOA_8/` 目录内（大文件不在 Git 中，联系 **2827883762@qq.com** 获取）：

```
tests/data/GOA_8/
├── GOA_8.csv              # 样本信息 (56样本)
├── GOA_8_HQ_R1.fq.gz     # FASTQ R1 (大文件，需单独获取)
├── GOA_8_HQ_R2.fq.gz     # FASTQ R2 (大文件，需单独获取)
└── GOA_8_Results_Txt/     # 预期结果文件 (50个，用于突变分析测试)
```
