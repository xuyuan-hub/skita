#!/usr/bin/env python

import os
import sys

import pandas as pd

# 序列读数百分比 <0.2 时，不加入比对图谱
PLOT_CUTOFF_FREQ = 0.2

# 给片段去重
def unique_func(words):
    result_word_list = sorted(list(words))
    result_words = []
    for rws in result_word_list:
        if rws not in result_words:
            result_words.append(rws)
    result_words = ''.join(result_words)
    return result_words

def describe_sequence_variation(aligned_seq, reference_seq):
    """
    针对每条序列进行突变类型描述。包括XX缺失/插入，nbp缺失/插入，片段缺失/插入等。

    Args:
    aligned_seq (str): The sequence obtained from the experiment.
    reference_seq (str): The reference sequence to compare against.

    Returns:
    description (str): 突变类型的描述
    is_frameshift (boolean): 是否为移码突变

    """
    deletions_position = [i for i, char in enumerate(aligned_seq) 
                            if char == '-']
    insertions_position = [i for i, char in enumerate(reference_seq) 
                            if char == '-']
    
    # 1. 存在缺失
    if len(deletions_position) > 0:
        # n == 1 或者 n == 2 时，描述为 X缺失 或者 XX缺失（具体碱基）
        if len(deletions_position) < 3:
            deletions_base = "".join([reference_seq[i] for i in deletions_position])
            deletions_base = unique_func(deletions_base)
            description = deletions_base + "缺失"
            is_frameshift = True
        # n >= 3 时，描述为 nbp缺失 ，如存在边界缺失，描述为 片段缺失
        if len(deletions_position) >= 3:
            if (
                0 in deletions_position
                or len(aligned_seq) - 1 in deletions_position
            ):
                description = "片段缺失"
                is_frameshift = False
            else:
                deletions_num = len(deletions_position)
                change_base = "".join([reference_seq[i] for i in deletions_position])
                change_base = unique_func(change_base)
                # description = str(deletions_num) + "bp缺失," + change_base + "缺失"
                description = str(deletions_num) + "bp缺失"
                if deletions_num % 3 == 0:
                    is_frameshift = False
                else:
                    is_frameshift = True

    # 2. 存在插入
    if len(insertions_position) > 0:
        # n == 1 或者 n == 2 时，描述为 X插入 或者 XX插入（具体碱基）
        if len(insertions_position) < 3:
            insertions_base = "".join([aligned_seq[i] for i in insertions_position])
            description = insertions_base + "插入"
            is_frameshift = True
        # n >= 3 时，描述为 nbp插入 ，如存在边界插入，描述为 片段插入
        if len(insertions_position) >= 3:
            if (
                0 in insertions_position
                or len(reference_seq) - 1 in insertions_position
            ):
                description = "片段插入"
                is_frameshift = False
            else:
                insertions_num = len(insertions_position)
                change_base = "".join([aligned_seq[i] for i in insertions_position])
                change_base = unique_func(change_base)
                # description = str(insertions_num) + "bp插入," + change_base + "插入"
                description = str(insertions_num) + "bp插入"
                if insertions_num % 3 == 0:
                    is_frameshift = False
                else:
                    is_frameshift = True
    
    # 3. 除以上2种类别外，描述为WT
    if len(deletions_position) == 0 and len(insertions_position) == 0:
        description = "WT"
        is_frameshift = False
    
    # 4. 如果既存在缺失，也存在插入，应描述为 nbp缺失/插入
    if len(deletions_position) > 0 and len(insertions_position) > 0:
        diff = len(deletions_position) - len(insertions_position)
        if diff > 0:
            description = str(diff) + "bp缺失"
        elif diff == 0:
            description = "WT"
        else:
            description = str(-diff) + "bp插入"
        
        if diff % 3 == 0:
            is_frameshift = False
        else:
            is_frameshift = True


    return description, is_frameshift


def interpret_description_one(descriptions, id):
    """
    针对一条数据的判读。

    Args:
    descriptions (list): A list of descriptions.
    id (str): 种质编号

    Returns:
    interpretations (str)

    """
    # 只有1条数据，直接判读
    description, is_frameshift, reads = (
        descriptions[0]["description"], 
        descriptions[0]["is_frameshift"], 
        descriptions[0]["reads"]
    )

    if not is_frameshift:
        interpretations = "无突变"
    else:
        if reads < 200:
            interpretations = "有突变, " + description
        else:
            interpretations = "纯合突变, " + description
    
    print(id + "\t" + interpretations)
    final_result = id + "\t" + interpretations
    return final_result


def interpret_description_two(descriptions, id):
    """
    针对两条数据的判读。

    Args:
    descriptions (list): A list of descriptions.
    id (str): 种质编号

    Returns:
    interpretations (str)

    """
    # 第2条占比 >= 10% 或者 非移码突变，判读2条数据
    if (
        descriptions[1]["reads_pct"] >= 10
        or not descriptions[1]["is_frameshift"]
    ):
        descriptions_list = ([
            descriptions[0]["description"],
            descriptions[1]["description"]
        ])
        
        # 辅助规则：去重
        descriptions_list = list(dict.fromkeys(descriptions_list))

        # 辅助规则：把 WT 写到前面
        if "WT" in descriptions_list:
            descriptions_list.remove("WT")
            descriptions_list.insert(0, "WT")

        # 2条均为非移码，则为无突变
        if (
            not descriptions[0]["is_frameshift"] 
            and not descriptions[1]["is_frameshift"]
        ):
            interpretations = "无突变"
        # 2条均为移码
        elif (
            descriptions[0]["is_frameshift"]
            and descriptions[1]["is_frameshift"]
            and descriptions[0]["reads"] >= 200
            and descriptions[1]["reads"] >= 200
        ):
            interpretations = (
                "双等位突变，" 
                + '/'.join(descriptions_list)
            )
        # 1条移码，1条WT（非移码）
        elif (
            descriptions[0]["description"] == "WT"
            or descriptions[1]["description"] == "WT"
        ) and (
            descriptions[0]["reads"] >= 200
            and descriptions[1]["reads"] >= 200
        ):
            interpretations = (
                "杂合突变，"
                + '/'.join(descriptions_list)
            )
        # 其他情况，有突变
        else:
            interpretations = (
                "有突变，" 
                + '/'.join(descriptions_list)
            )
    # 第2条占比低于10%且移码，仅判读第1条数据
    else:
        if not descriptions[0]["is_frameshift"]:
            interpretations = "无突变"
        else:
            interpretations = "有突变," + descriptions[0]["description"]
    
    print(id + "\t" + interpretations)
    final_result = id + "\t" + interpretations
    return final_result


def interpret_description_three(descriptions, id):
    """
    针对三条数据的判读。

    Args:
    descriptions (list): A list of descriptions.
    id (str): 种质编号

    Returns:
    interpretations (str)

    """
    descriptions_list = [descriptions[0]["description"]]
    mutation_flag = descriptions[0]["is_frameshift"]

    # 第2条占比 >= 10% 或者 非移码突变，加入第2条数据进行判读
    if (
        descriptions[1]["reads_pct"] >= 10
        or not descriptions[1]["is_frameshift"]
    ):
        descriptions_list.append(descriptions[1]["description"])
        # 存在任一判读序列为移码，则为有突变
        mutation_flag = mutation_flag or descriptions[1]["is_frameshift"]
    
    # 第3条占比 >= 10% 或者 非移码突变，加入第3条数据进行判读
    # 增加规则：如果已有非移码突变，不再加入占比<10%的非移码突变
    if (
        descriptions[2]["reads_pct"] >= 10
        or (
            not descriptions[2]["is_frameshift"] 
            and descriptions[0]["is_frameshift"]
            and descriptions[1]["is_frameshift"]
        )
    ):
        descriptions_list.append(descriptions[2]["description"])
        # 存在任一判读序列为移码，则为有突变
        mutation_flag = mutation_flag or descriptions[2]["is_frameshift"]

    # 辅助规则：去重
    descriptions_list = list(dict.fromkeys(descriptions_list))

    # 辅助规则：把 WT 写到前面
    if "WT" in descriptions_list:
        descriptions_list.remove("WT")
        descriptions_list.insert(0, "WT")

    if mutation_flag:
        interpretations = "有突变，" + "/".join(descriptions_list)
    else:
        interpretations = "无突变"
    
    print(id + "\t" + interpretations)
    final_result = id + "\t" + interpretations
    return final_result


def process_file_content(file_path):
    """
    读取每个txt编号序列文档。提取前3行数据。

    Args:
    file_path (str): The path to the txt file.

    """
    lines_of_interests = []
    # 兼容 Windows 和 Unix 路径分隔符
    basename = os.path.basename(file_path)
    id = basename[: basename.rfind(".txt")]
    
    with open(file_path, 'r') as file:
        for i, line in enumerate(file):
            # 最多判读3条数据
            if i >= 1 and i <= 3:
                lines_of_interests.append(line.strip())
    
    descriptions = []
    for i, line in enumerate(lines_of_interests):
        columns = line.strip().split('\t')
        aligned_seq, reference_seq = columns[0], columns[1]
        reads, reads_pct = columns[-2], columns[-1]

        if float(reads_pct) < PLOT_CUTOFF_FREQ:
            continue

        if len(aligned_seq) != len(reference_seq):
            print("Warning: 序列长度不一致! ")

        description, is_frameshift =  describe_sequence_variation(
            aligned_seq, reference_seq
        )
        descriptions.append(
            {
                "description": description, 
                "is_frameshift": is_frameshift,
                "reads": int(reads),
                "reads_pct": float(reads_pct)
            }
        )

    if len(descriptions) == 1:
        result_word = interpret_description_one(descriptions, id)
    elif len(descriptions) == 2:
        result_word = interpret_description_two(descriptions, id)
    elif len(descriptions) == 3:
        result_word = interpret_description_three(descriptions, id)
    return result_word


def process_all_txt_files(folder_path):
    """
    读取指定文件夹下的所有txt编号序列文档。

    Args:
    folder_path (str): The path to the folder containing txt files.

    """
    # 从文件夹名提取项目名 (如 SA_Results_Txt -> SA)
    folder_basename = os.path.basename(folder_path.rstrip("/\\"))
    project_name = folder_basename.split("_")[0]
    output_path = os.path.join(os.path.dirname(folder_path), project_name + "_mutation.tsv")

    with open(output_path, "w", encoding="utf-8") as file:
        for file_name in os.listdir(folder_path):
            if file_name.endswith('.txt'):
                file_path = os.path.join(folder_path, file_name)
                final_word = process_file_content(file_path)
                file.write(str(final_word)+"\n")

    print(f"\n结果已保存至: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='describe sequence')
    parser.add_argument("--path", type=str, default=None)
    args = parser.parse_args()
    process_all_txt_files(args.path)


