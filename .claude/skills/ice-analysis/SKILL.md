---
name: ice-analysis
description: 使用 Synthego ICE 从 Sanger 测序数据推断 CRISPR 编辑结果。当用户需要分析 CRISPR 编辑效率、检测 indels、评估 HDR、分析 Sanger 测序的 CRISPR 实验结果时使用此 skill。支持单个样本和批量分析，输出编辑效率、indel 分布、序列贡献等。
---

# ICE - CRISPR 编辑分析

使用 Synthego ICE (Inference of CRISPR Edits) 从 Sanger 测序数据推断 CRISPR 编辑结果。

## 何时使用

- 用户说"分析 CRISPR 编辑"、"Sanger 测序 CRISPR"、"ICE 分析"
- 用户有对照样本和编辑样本的 .ab1 文件
- 用户需要评估 CRISPR 编辑效率
- 用户需要检测 indels（插入/缺失）

## 与 crispr-mutation 的区别

| Skill | 数据类型 | 用途 |
|-------|----------|------|
| **crispr-mutation** | NGS (FASTQ) | 深度测序，高精度突变分析 |
| **ice-analysis** | Sanger (.ab1) | 快速筛查，编辑效率评估 |

## 依赖安装

synthego-ice 与主环境存在依赖冲突（锁定 pytest==5.2.2），必须使用 skill 级虚拟环境：

```bash
# 创建 skill venv（仅首次）
python -m venv .claude/skills/ice-analysis/.venv

# 安装依赖（--no-deps 避免 sklearn 构建失败）
.claude/skills/ice-analysis/.venv/Scripts/pip install synthego-ice --no-deps
.claude/skills/ice-analysis/.venv/Scripts/pip install biopython numpy pandas scipy scikit-learn matplotlib xlsxwriter xlrd

# 修复 Biopython 兼容性
.claude/skills/ice-analysis/.venv/Scripts/python .claude/skills/ice-analysis/scripts/patch_ice.py
```

> 所有 ICE 命令必须通过 `.claude/skills/ice-analysis/.venv/Scripts/` 下的可执行文件运行。

## 输入要求

### 必需文件

| 文件 | 说明 |
|------|------|
| **对照样本** (.ab1) | 未编辑的野生型 Sanger 测序文件 |
| **编辑样本** (.ab1) | CRISPR 处理后的 Sanger 测序文件 |
| **gRNA 目标序列** | 17-23 bp 的 protospacer 序列 |

### 可选文件

| 文件 | 说明 |
|------|------|
| **Donor 序列** | HDR 分析时需要的供体 DNA 序列 |

## 分析流程

```
control.ab1 + edited.ab1 + gRNA 序列
    ↓
ICE 非负最小二乘回归 (NNLS)
    ↓
输出:
  - 总体编辑效率
  - Indel 分布图
  - Discordance 图
  - 序列贡献表
  - 标注的 Sanger 色谱图
```

## 使用方式

### 单个样本分析

```bash
.claude/skills/ice-analysis/.venv/Scripts/synthego_ice \
    --control data/control.ab1 \
    --edited data/edited.ab1 \
    --target AACCAGTTGCAGGCGCCCCA \
    --out data/workspace/ice-analysis/<项目名>/sample1
```

> `--out` 必须指向 `data/workspace/ice-analysis/`，分析完成后通过 `Files.save()` 将重要文件归档到 `data/files/`。

### 批量分析

准备 Excel 文件 (`samples.xlsx`)：

| Sample | Control | Edited | Target |
|--------|---------|--------|--------|
| sample1 | control1.ab1 | edited1.ab1 | AACCAGTTGCAGGCGCCCCA |
| sample2 | control2.ab1 | edited2.ab1 | GCTAGCTAGCTAGCTAGCTA |

运行批量分析：

```bash
.claude/skills/ice-analysis/.venv/Scripts/synthego_ice_batch \
    --in samples.xlsx \
    --data data/ \
    --out data/workspace/ice-analysis/<项目名>/
```

### Python 调用

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path('.claude/skills/ice-analysis/scripts').resolve()))

from ice_wrapper import ICEAnalyzer

analyzer = ICEAnalyzer(
    control=Path('data/control.ab1'),
    edited=Path('data/edited.ab1'),
    target='AACCAGTTGCAGGCGCCCCA',
    output_dir=Path('results'),
)

result = analyzer.run()
print(f"编辑效率: {result.editing_efficiency:.1%}")
print(f"Indels: {result.indel_summary}")
```

## 输出结果

### 1. 编辑效率 (editing_efficiency)

```
总体编辑效率: 78.5%
- 缺失 (deletions): 65.2%
- 插入 (insertions): 10.3%
- 野生型 (WT): 21.5%
```

### 2. 序列贡献表

```
Relative contribution of each sequence (normalized)
--------------------------------------------------------
0.3006   -1[g1]   CCCAACACAACCAGTTGCAGGCGCC|-CATGGTGAGCA...
0.1996   0[g1]    CCCAACACAACCAGTTGCAGGCGCC|CCATGGTGAGCA...
0.1818   1[g1]    CCCAACACAACCAGTTGCAGGCGCC|nCCATGGTGAGC...
```

### 3. 输出文件

| 文件 | 内容 |
|------|------|
| `*_trace.json` | 色谱图数据 |
| `*_discordance.json` | 信号一致性分析 |
| `*_indel.json` | Indel 分布数据 |
| `*_aligned_reads.txt` | 比对结果 |
| `*.png` | 可视化图表 |

## Schema 定义

- `meta/ice_run.json` - 运行记录
- `meta/ice_result.json` - 样本结果

## 数据存储

分析完成后自动：
1. 将结果存入 `data/skita.db`（表：`data_ice_run`, `data_ice_result`）
2. 归档文件到 `data/files/ice-analysis/`

## 测试

测试文件：`tests/test_ice.py`，使用 `tests/data/good_example_*.ab1` 测试数据。

```bash
python -m pytest .claude/skills/ice-analysis/tests/test_ice.py -v
```

### 测试用例

| 测试 | 断言 |
|------|------|
| `test_synthego_ice_runs_successfully` | 命令正常退出 (returncode=0) |
| `test_output_files_generated` | 8 个输出文件完整生成且非空 |
| `test_editing_efficiency` | 编辑效率 = 77.0% |
| `test_r_squared` | R² >= 0.98 |
| `test_indel_distribution` | -1bp=37%, 0(WT)=21%, +1bp=18%, -2bp=12%, +2bp=4%, -16bp=3%, -4bp=2%, -3bp=1% |
| `test_wt_deletion_insertion_sum` | 所有 indel 类型之和 ≈ 100% (±2%) |
| `test_contribs_top_sequences` | 序列贡献表非空 |
| `test_discord_plot_has_cut_site` | 切割位点=231，discordance 数据完整 |

### 测试数据参考值 (good_example)

- gRNA: `AACCAGTTGCAGGCGCCCCA`
- 编辑效率: 77.0%，R²: 0.98
- WT: 21%，Deletions: 55%，Insertions: 22%

## 在线版本

如果不想本地安装，可以使用 Synthego 提供的免费在线版本：
https://ice.synthego.com

在线版支持批量分析、图表生成和样本 QC。

## 参考文献

1. Brinkman et al. "Easy quantitative assessment of genome editing by sequence trace decomposition." Nucleic Acids Res. 2014
2. Hsiau et al. "Inference of CRISPR Edits from Sanger Trace Data." BioRxiv. 2018

## 故障排除

### 编辑效率为 0

可能原因：
- gRNA 序列不正确
- 对照和编辑样本不匹配
- 测序质量太差

### 安装失败

```bash
# 尝试使用 conda
conda install -c bioconda synthego-ice

# 或使用 Docker
docker pull synthego/ice:latest
```

### Biopython >= 1.82 兼容性问题

**错误现象**：
```
AttributeError: 'MultipleSeqAlignment' object has no attribute 'format'
```

**原因**：Biopython 1.82+ 移除了 `MultipleSeqAlignment.format()` 方法，而 ICE (synthego-ice 1.2.0) 在 `ice/classes/pair_alignment.py` 第 80 行调用了该方法。

**解决方案**：运行自动 patch 脚本：

```bash
python .claude/skills/ice-analysis/scripts/patch_ice.py
```

脚本会自动定位 ICE 包位置、检测是否已修复、执行补丁。重新安装 ICE 后需再次运行。

### 找不到 ab1 文件

确保文件路径正确，Excel 中的文件名与实际文件名一致。
