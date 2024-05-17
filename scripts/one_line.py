import sys
import os
import re


                      
def split_article(text):
    """
    将长字符串分为符合正则表达式"{[^{}\[\]=]+zh[^{}\[\]=]+}"的多个片段,
    从中提取形如{H|zh-cn:计算机; zh-sg:电脑; zh-tw:電腦;}的内容为字典。

    参数:
    text (str): 要分割的长字符串
    
    返回:
    tuple: 包含两个列表的元组,
           第一个字典为 其他语言-简中
           第二个列表是待保存的文本。如果匹配到的内容保存到了字典中，则该段内容替换后仅剩余简中；否则不执行任何动作
    """
    pattern = r'\{[^{}\[\]=]+zh[^{}\[\]=]+\}'
    matches = re.findall(pattern, text)
    
    # 创建一个字典来存储 key 和其对应的值
    PATTERN = r'(zh-hans|zh-cn):([^;]+)'
    dictionary = {}
    result = []
    keys = []
    values = []
    for line in matches:
        string = line.strip()[1:-1].replace("H|","")
        # 捕获简中关键字
        match = re.search(PATTERN, string)
        if match:
            key = match.group(2).strip()
            if len(key) >= 2 and len(key)<=30 and  any(ord(c) >= 128 for c in key):
                # 遍历各个区域
                locales = string.split(';')
                if len(locales) > 1:
                    for locale in locales:
                        if len(locale) >= 2:
                            parts = locale.split(':', 1)
                            if len(parts) == 2:
                                lang, value = parts
                                value = value.strip()
                                if key != value:
                                    dictionary[value] = key
                                    values.append(key)
                                    keys.append(value)
                        # else:
                        #     print(f"Warning: Skipping locale with length < 2: {locale}")
                else:
                    print(f"Warning: Skipping string with < 2 locales: {string}")
            
    for i in range(len(keys)):
        text = text.replace(keys[i],values[i])
    
    return dictionary, text
 


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
  dictionary = {}
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
          dic, text = split_article(output_line)
          dictionary.update(dic)
          with open(output_filename, 'a') as output_file:
            output_file.write(text + '\n')
          continue
      elif all(ord(char) < 128 for char in line):
        continue
      else:
        buffer += re.sub(pattern, ' ', line)

  if total_sections == 0:
    return dictionary, total_sections, output_sections, 0.00
  return dictionary, total_sections, output_sections, round(output_sections / total_sections * 100, 2)

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
    dictionary = {}
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path) and not "." in filename:
            output_filename = os.path.splitext(file_path)[0] + '.txt'
            dic, total_sections, output_sections, percentage = wikiextractor_xml2txt(file_path, output_filename, min_length)
            print(f'Input: {total_sections}, Output: {output_sections}, Percentage: {percentage}%, dict: {len(dic)} File: {filename}\n')
            dictionary.update(dic)
            
    from collections import OrderedDict
    # 根据键排序字典
    sorted_dict = OrderedDict(sorted(dictionary.items(), key=lambda x: x[0]))
    n = 0
    with open(f"scripts/wiki.opencc.txt", 'w') as output_file, open(f"scripts/wiki2.opencc.txt", 'w') as output_file2:
        for key, value in sorted_dict.items():
            if any(char.isspace() for char in key) or any(char.isspace() for char in value) :
                output_file2.write(key+"\t"+value + '\n')
            else :
                output_file.write(key+"\t"+value + '\n')
                n+=1
    print(f'Write OpenCC: {n}/{len(dictionary)}')
if __name__ == "__main__":
    main()
