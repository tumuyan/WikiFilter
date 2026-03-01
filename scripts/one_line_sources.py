#!/usr/bin/env python3
"""
追踪循环引用链条中每一级的原始记录，并保存到增强版 wiki1.opencc.txt

用法: python find_cyclic_sources.py <extracted-folder> <wiki1.opencc.txt> [wiki.opencc.txt]
"""
import sys
import os
import re
from wiki_utils import split_article


def load_cyclic_entries(filepath):
    """
    加载 wiki1.opencc.txt 中的循环引用词条
    
    返回:
        dict: key -> (value, final_value) 的映射
    """
    entries = {}
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                key, value, final_value = parts[0], parts[1], parts[2]
                entries[key] = (value, final_value)
    return entries


def load_all_mappings(filepath):
    """
    加载 wiki.opencc.txt 中的所有映射关系
    
    返回:
        dict: key -> value 的映射
    """
    mappings = {}
    if not os.path.exists(filepath):
        return mappings
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                mappings[parts[0]] = parts[1]
    return mappings


def build_chain(key, cyclic_entries, all_mappings, visited=None):
    """
    构建循环引用链条
    
    返回:
        list: [(from_key, to_value), ...] 链条中的每一级映射
    """
    if visited is None:
        visited = set()
    
    chain = []
    current = key
    
    while current and current not in visited:
        visited.add(current)
        
        # 先检查是否在 cyclic_entries 中
        if current in cyclic_entries:
            value, _ = cyclic_entries[current]
            chain.append((current, value))
            current = value
        # 再检查是否在 all_mappings 中
        elif current in all_mappings:
            value = all_mappings[current]
            chain.append((current, value))
            current = value
        else:
            break
    
    return chain


def find_all_sources(folder_path, target_keys):
    """
    在文件夹中查找所有目标 key 的原始来源
    按 <doc> 标签分段读取
    
    返回:
        dict: key -> list of original_line
    """
    found_sources = {}
    pattern = r'\s[\x09-~]+\s'
    
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if not os.path.isfile(file_path):
            continue
        
        print(f"  处理文件: {filename} ...", file=sys.stderr)
        
        with open(file_path, 'r') as f:
            buffer = ""
            for line in f:
                if line.startswith('<doc'):
                    buffer = ""
                    continue
                elif line.startswith('</doc>'):
                    if len(buffer) > 100:
                        output_line = buffer.replace('\n', ' ')
                        output_line = re.sub(r"[・･ᐧ]", "·", output_line)
                        
                        _, _, _, matches_list = split_article(output_line, return_matches=True)
                        
                        for original_line, local_dict in matches_list:
                            for key, value in local_dict.items():
                                if key in target_keys:
                                    if key not in found_sources:
                                        found_sources[key] = []
                                    # 只保留唯一的原始片段
                                    if original_line not in [s[0] for s in found_sources[key]]:
                                        found_sources[key].append((original_line, value))
                    continue
                elif all(ord(char) < 128 for char in line):
                    continue
                else:
                    buffer += re.sub(pattern, ' ', line)
    
    return found_sources


def main():
    if len(sys.argv) < 3:
        print("用法: python find_cyclic_sources.py <extracted-folder> <wiki1.opencc.txt> [wiki.opencc.txt]")
        print("  extracted-folder: wiki 数据文件夹路径")
        print("  wiki1.opencc.txt: 循环引用词条文件路径")
        print("  wiki.opencc.txt: (可选) 所有映射关系文件路径")
        return

    folder_path = sys.argv[1]
    cyclic_file = sys.argv[2]
    mappings_file = sys.argv[3] if len(sys.argv) > 3 else "scripts/wiki.opencc.txt"

    if not os.path.isdir(folder_path):
        print(f"错误: 文件夹不存在: {folder_path}")
        return

    if not os.path.exists(cyclic_file):
        print(f"错误: 文件不存在: {cyclic_file}")
        return

    print(f"加载循环引用词条: {cyclic_file}")
    cyclic_entries = load_cyclic_entries(cyclic_file)
    print(f"共加载 {len(cyclic_entries)} 条循环引用词条")

    print(f"加载映射关系: {mappings_file}")
    all_mappings = load_all_mappings(mappings_file)
    print(f"共加载 {len(all_mappings)} 条映射关系")

    # 构建所有循环引用链条，收集需要查找的所有 key
    all_chains = {}
    all_target_keys = set()
    
    for key in cyclic_entries.keys():
        chain = build_chain(key, cyclic_entries, all_mappings)
        all_chains[key] = chain
        for from_key, _ in chain:
            all_target_keys.add(from_key)
    
    print(f"\n需要查找 {len(all_target_keys)} 个 key 的原始来源")

    # 查找所有来源
    print(f"\n搜索原始来源: {folder_path}")
    found_sources = find_all_sources(folder_path, all_target_keys)
    print(f"找到 {len(found_sources)} 个 key 的来源")

    # 保存增强版 wiki1.opencc.txt
    # 生成新文件名
    base, ext = os.path.splitext(cyclic_file)
    output_file = f"{base}.detailed{ext}"
    
    with open(output_file, 'w') as f:
        f.write("# wiki1.opencc.txt 存在循环/链式引用的词条\n")
        f.write("# 格式: key\\tvalue\\tfinal_value\n")
        f.write("# 随后是每一级映射的原始片段\n\n")
        
        for key in sorted(all_chains.keys()):
            chain = all_chains[key]
            if not chain:
                continue
            
            # 第一行：key -> value -> final_value
            value, final_value = cyclic_entries[key]
            f.write(f"{key}\t{value}\t{final_value}\n")
            
            # 每一级映射的原始片段
            for from_key, to_value in chain:
                if from_key in found_sources:
                    for original_line, matched_value in found_sources[from_key]:
                        if matched_value == to_value:
                            f.write(f"  {original_line}\t# {from_key}->{to_value}\n")
                            break  # 只写第一个匹配的
            
            f.write("\n")
    
    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    main()
