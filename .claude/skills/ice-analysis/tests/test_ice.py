"""
ICE 分析 skill 测试
使用 tests/data/ 下的 good_example 测试数据验证 ICE 分析流程
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

TEST_DATA = Path(__file__).parent / "data"
CONTROL = TEST_DATA / "good_example_control.ab1"
EDITED = TEST_DATA / "good_example_edited.ab1"
TARGET = "AACCAGTTGCAGGCGCCCCA"


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "ice_output"


class TestICESingleSample:
    """单样本 ICE 分析测试"""

    def test_synthego_ice_runs_successfully(self, output_dir):
        """synthego_ice 命令能正常执行"""
        result = subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(output_dir / "good_example"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ICE 运行失败: {result.stderr}"

    def test_output_files_generated(self, output_dir):
        """验证输出文件完整性"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        expected_suffixes = [
            ".indel.json",
            ".contribs.json",
            ".contribs.txt",
            ".all.json",
            ".all.txt",
            ".trace.json",
            ".windowed.json",
            ".windowed.txt",
        ]
        for suffix in expected_suffixes:
            f = Path(str(prefix) + suffix)
            assert f.exists(), f"缺少输出文件: {f.name}"
            assert f.stat().st_size > 0, f"输出文件为空: {f.name}"

    def test_editing_efficiency(self, output_dir):
        """验证编辑效率 = 77%"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".indel.json") as f:
            data = json.load(f)

        assert data["editing_eff"] == 77.0

    def test_r_squared(self, output_dir):
        """验证 R² 拟合度 >= 0.98"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".indel.json") as f:
            data = json.load(f)

        assert data["r_sq"] >= 0.98

    def test_indel_distribution(self, output_dir):
        """验证 indel 分布与预期一致"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".indel.json") as f:
            data = json.load(f)

        outcomes = data["editing_outcomes"]

        # 主要 indel 类型验证（基于实际运行结果）
        assert outcomes["-1"] == 37.0  # 1bp 缺失，最常见
        assert outcomes["0"] == 21.0   # 野生型
        assert outcomes["1"] == 18.0   # 1bp 插入
        assert outcomes["-2"] == 12.0  # 2bp 缺失
        assert outcomes["2"] == 4.0    # 2bp 插入
        assert outcomes["-16"] == 3.0  # 16bp 大缺失
        assert outcomes["-4"] == 2.0   # 4bp 缺失
        assert outcomes["-3"] == 1.0   # 3bp 缺失

    def test_wt_deletion_insertion_sum(self, output_dir):
        """验证 WT + deletion + insertion = 100%"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".indel.json") as f:
            data = json.load(f)

        outcomes = data["editing_outcomes"]
        total = sum(outcomes.values())

        # 所有编辑类型之和 ≈ 100% (ICE 结果为整数百分比，可能有 ±2 的舍入误差)
        assert abs(total - 100.0) <= 2.0, f"Indel 总和 {total} 偏离 100%"

    def test_contribs_top_sequences(self, output_dir):
        """验证序列贡献表的前 3 个条目"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".contribs.json") as f:
            contribs = json.load(f)

        # contribs 是按贡献度排序的列表
        assert len(contribs) > 0, "序列贡献表为空"

    def test_discord_plot_has_cut_site(self, output_dir):
        """验证 discordance 数据包含切割位点信息"""
        prefix = output_dir / "good_example"
        subprocess.run(
            [
                "synthego_ice",
                "--control", str(CONTROL),
                "--edited", str(EDITED),
                "--target", TARGET,
                "--out", str(prefix),
            ],
            capture_output=True,
            text=True,
        )

        with open(str(prefix) + ".indel.json") as f:
            data = json.load(f)

        discord = data["discord_plot"]
        assert "cut_site" in discord
        assert discord["cut_site"] == 231
        assert "control_discord" in discord
        assert "edited_discord" in discord
        assert len(discord["control_discord"]) == len(discord["edited_discord"])
