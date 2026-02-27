"""
自动修复 ICE 与 Biopython >= 1.82 的兼容性问题。

问题：Biopython 1.82+ 移除了 MultipleSeqAlignment.format() 方法，
      ICE 在 pair_alignment.py 中调用了该方法导致 AttributeError。

用法：
    python .claude/skills/ice-analysis/scripts/patch_ice.py
"""

import importlib.util
import sys
from pathlib import Path

PATCH_MARKER = "_AIO.write(aln_objs[0], _buf"

OLD_CODE = 'alignment_txt = aln_objs[0].format("clustal").split(\'\\n\', 2)[2]'

NEW_CODE = """try:
            alignment_txt = aln_objs[0].format("clustal").split('\\n', 2)[2]
        except AttributeError:
            from io import StringIO as _SIO
            from Bio import AlignIO as _AIO
            _buf = _SIO()
            _AIO.write(aln_objs[0], _buf, "clustal")
            alignment_txt = _buf.getvalue().split('\\n', 2)[2]"""


def find_ice_package() -> Path | None:
    spec = importlib.util.find_spec("ice")
    if spec and spec.submodule_search_locations:
        return Path(spec.submodule_search_locations[0])
    return None


def patch():
    ice_path = find_ice_package()
    if not ice_path:
        print("ICE 包未安装，跳过 patch。")
        print("安装方法: pip install synthego-ice")
        return False

    target = ice_path / "classes" / "pair_alignment.py"
    if not target.exists():
        print(f"找不到目标文件: {target}")
        return False

    content = target.read_text(encoding="utf-8")

    if PATCH_MARKER in content:
        print(f"已修复，跳过: {target}")
        return True

    if OLD_CODE not in content:
        print(f"目标代码未找到（可能 ICE 版本不同）: {target}")
        return False

    patched = content.replace(OLD_CODE, NEW_CODE, 1)
    target.write_text(patched, encoding="utf-8")
    print(f"修复成功: {target}")
    return True


if __name__ == "__main__":
    success = patch()
    sys.exit(0 if success else 1)
