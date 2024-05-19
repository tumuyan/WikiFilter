import sys
import os
import re

import os
import sys
from itertools import takewhile

def split_file(input_file, output_dir, num_files):
    # 计算每个小文件的大约大小
    input_size = os.path.getsize(input_file)
    file_size = input_size // num_files
    i=0
    output_file = os.path.join(output_dir, f'wiki_{i:02}.txt')
    of = open(output_file, 'w', encoding='utf-8')
    # total = 0

    # 打开输入文件并分块读取
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = []
        current_size = 0
        for line in f:
            of.write(line)
            line_size = len(line.encode('utf-8'))
            current_size += line_size
            # total += line_size
            if current_size >= file_size:
                of.close()
                current_size = 0
                i+=1
                output_file = os.path.join(output_dir, f'wiki_{i:02}.txt')
                of = open(output_file, 'w', encoding='utf-8')
    of.close()

    print(f'文件已成功分割为{i+1}个小文件到{output_dir}')

def main():
    if len(sys.argv) < 3:
        print("Usage: python script.py <input-path> <folder-path> <output-number>")
        print("  input-path: 输入的文件路径")
        print("  folder-path: 输出的文件路径")
        print("  output-number: 输出的文件数量")
        return
        
    input_path = sys.argv[1]
    folder_path = sys.argv[2]
    output_number = 1
    if len(sys.argv) > 3:
        output_number = int(sys.argv[3])

    split_file(input_path, folder_path, output_number)
if __name__ == "__main__":
    main()
