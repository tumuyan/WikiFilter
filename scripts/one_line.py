import sys
import os
import re

# 逐行读取指定文件。文件分为多个部分，每个部分都以<doc 开头，以</doc>结尾。读取一个部分后，如果这个部分的长度大于指定值，则把缓存的内容中的换行改为空格，作为新的一行内容输出到指定文件

def wikiextractor_xml2txt(filename, output_filename, min_length):
  """
  逐行读取指定文件，处理符合条件的部分，并输出到指定文件。

  Args:
    filename: 要读取的文件名。
    output_filename: 处理后的内容输出到的文件名。
    min_length: 部分的最小长度。

  Returns:
    一个元组，包含总共处理了多少个部分，最终输出了多少个部分，比例是多少。
  """

  total_sections = 0
  output_sections = 0

  pattern = r'\s[\x09-~]+\s'
 
  with open(filename, 'r') as f:
    buffer = ""
    for line in f:
      if line.startswith('<doc'):
        total_sections += 1
        buffer = ""
        continue
      elif line.startswith('</doc>'):
        if len(buffer) > min_length:
          output_sections += 1
          # 把缓存的内容中的换行改为空格，作为新的一行内容输出到指定文件。
          output_line = buffer.replace('\n', ' ')
          with open(output_filename, 'a') as output_file:
            output_file.write(output_line + '\n')
          continue
      elif all(ord(char) < 128 for char in line):
        continue
      else:
        buffer += re.sub(pattern, ' ', line)

  return total_sections, output_sections, round(output_sections / total_sections * 100, 2)

# # 使用示例
# filename = '/content/wiki2/text/AA/wiki_00'
# output_filename = '/content/wiki2/text/AA/wiki_00_output.txt'
# min_length = 100

# total_sections, output_sections, percentage = wikiextractor_xml2txt(filename, output_filename, min_length)

# print(f'Total sections: {total_sections}')
# print(f'Output sections: {output_sections}')
# print(f'Percentage: {percentage}%')


# 遍历文件夹，对后缀不是txt和csv的文件运行wikiextractor_xml2txt()
# 处理后打印总共处理了多少个部分，最终输出了多少个部分，比例是多少

import os
# 使用示例
# folder_path = 'text/AA'
# min_length = 100
def main():
    if len(sys.argv) < 3:
        print("Usage: python script.py <folder-path> <mini-length>")
        print("  folder-path: 扫描的文件路径")
        print("  mini-length: 忽略文本长度小于设定值的文本")
        return

    folder_path = sys.argv[1]
    min_length = int(sys.argv[2])

    for filename in os.listdir(folder_path):
      file_path = os.path.join(folder_path, filename)
      if os.path.isfile(file_path) and not filename.endswith('.txt') and not filename.endswith('.csv'):
        output_filename = os.path.splitext(file_path)[0] + '.txt'
        total_sections, output_sections, percentage = wikiextractor_xml2txt(file_path, output_filename, min_length)
        print(f'Input: {total_sections}, Output: {output_sections}, Percentage: {percentage}%, File: {filename}')

if __name__ == "__main__":
    main()
