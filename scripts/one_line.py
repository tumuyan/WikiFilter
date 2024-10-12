import sys
import os
import re
from collections import OrderedDict
import opencc


def remove_punctuation_length(text):
    # 定义一个正则表达式模式，匹配所有中英文标点符号
    punctuation_pattern = r'[\u3000-\u303F\uFF00-\uFFEF\u2000-\u206F\u0021-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E]'
    # 使用正则表达式替换掉所有的标点符号
    cleaned_text = re.sub(punctuation_pattern, '', text)
    return len(cleaned_text) 

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
    pattern = r'\{[^\{\}\[\]\=]+zh[^\{\}\[\]\=]+\}'
    matches = re.findall(pattern, text)
    
    # 创建一个字典来存储 key 和其对应的值
    PATTERN = r'(zh-hans|zh-cn):([^;]+)'
    dictionary = {}
    result = []
    keys = []
    clips = []
    difference = set()
    for line in matches:
        # 去除{H|  }
        string = line.strip()[1:-1].strip()
        if len(text) >= 2 and text[1] == "|": 
            line = line[2]
        # 捕获简中关键字
        match = re.search(PATTERN, string)
        if match:
            key = match.group(2).strip()
            if remove_punctuation_length(key) >= 2 and len(key)<=30 and  any(ord(c) >= 128 for c in key):
                # 遍历各个区域
                locales = string.split(';')
                if len(locales) > 1:
                    record = True
                    for locale in locales:
                        if len(locale) >= 2:
                            parts = locale.split(':', 1)
                            if len(parts) == 2:
                                lang, value = parts
                                value = value.strip()
                                if key != value and len(value) >= 2 and len(value)<=30:
                                    if value in dictionary:
                                        if key!= dictionary[value]:
                                            difference.add(value+"\t"+key)
                                            difference.add(value+"\t"+dictionary[value])
                                    else:
                                        dictionary[value] = key
                                    if record:
                                        clips.append(line)
                                        keys.append(value)
                                        recorded = False

                        # else:
                        #     print(f"Warning: Skipping locale with length < 2: {locale}")
                else:
                    print(f"Warning: Skipping string with < 2 locales: {string}")
            
    for i in range(len(keys)):
        text = text.replace(clips[i],keys[i])

    return dictionary, text, difference
 


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
  difference = set()
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

          # 统一符号
          output_line = re.sub(r"[・･ᐧ]", "·", output_line)

          dic, text, dif = split_article(output_line)
          dictionary.update(dic)
          difference.update(dif)
          with open(output_filename, 'a') as output_file:
            output_file.write(text + '\n')
          continue
      elif all(ord(char) < 128 for char in line):
        continue
      else:
        buffer += re.sub(pattern, ' ', line)

  if total_sections == 0:
    return dictionary, difference, total_sections, output_sections, 0.00
  return dictionary, difference, total_sections, output_sections, round(output_sections / total_sections * 100, 2)

# 遍历文件夹，对后缀不是txt和csv的文件运行wikiextractor_xml2txt()
# 处理后打印总共处理了多少个部分，最终输出了多少个部分，比例是多少

def main():
    if len(sys.argv) < 3:
        print("Usage: python script.py <folder-path> <mini-length>")
        print("  folder-path: 扫描的文件路径")
        print("  mini-length: 忽略文本长度小于设定值的文本")
        return

    # 定义一个正则表达式模式, 用于匹配拼音
    pinyin_pattern = r'^[、\u0061-\u007A\u00E0-\u00E6\u00E8-\u00ED\u00F2-\u00F6\u00F9-\u00FC\u0100-\u3000]+$'
    
 

    folder_path = sys.argv[1]
    min_length = int(sys.argv[2])
    dictionary = {}
    difference = set()
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path) and not "." in filename:
            output_filename = os.path.splitext(file_path)[0] + '.txt'
            dic, dif, total_sections, output_sections, percentage = wikiextractor_xml2txt(file_path, output_filename, min_length)
            print(f'Input: {total_sections}, Output: {output_sections}, Percentage: {percentage}%, dict: {len(dic)} File: {filename}\n')
            dictionary.update(dic)
            difference.update(dif)


    skiplist = []
    # 读取黑名单
    file_path = f"scripts/blacklist.opencc.txt"
    if not os.path.exists(file_path):
        # 设置文本为红色
        print("\033[91mError: File '{}' does not exist.\033[0m".format(file_path))
    else:
        with open(file_path, 'r') as f:
            for line in f:
                word = line.split('\t',2)[0].strip()
                if len(word)>0:
                    skiplist.append(word)

    file_path = f"scripts/blacklist2.opencc.txt"
    if not os.path.exists(file_path):
        # 设置文本为红色
        print("\033[91mError: File '{}' does not exist.\033[0m".format(file_path))
    else:
        with open(file_path, 'r') as f:
            for line in f:
                word = line.split('\t',2)[0].strip()
                if len(word)>0:
                    skiplist.append(word)
    
    # 读取白名单
    # whitelist = []
    file_path = f"scripts/Translation.txt"
    if not os.path.exists(file_path):
        # 设置文本为红色
        print("\033[91mError: File '{}' does not exist.\033[0m".format(file_path))
    else:
        with open(file_path, 'r') as f:
            for line in f:
                word = line.split('\t',2)[0].strip()
                if len(word)>0:
                    # whitelist.append(word)
                    skiplist.append(word)


    # 保存opencc配置中存在冲突的内容
    difference_sort = sorted(list(difference))
    with open(f"scripts/wiki3.opencc.txt", 'w') as f, open(f"scripts/wiki4.opencc.txt", 'w') as f2:
        f2.write("# wiki4.opencc.txt 存在冲突的内容（同词条对应了多个简中结果）在Translation.txt和blacklist.opencc.txt中出现的词条也会出现在这个文件中。用于后期对词条重新检查。\n")
        f.write("# wiki3.opencc.txt 存在冲突的内容（同词条对应了多个简中结果）在Translation.txt和blacklist.opencc.txt中出现的词条不会出现在这个文件中。即使是剔除了有括号、有空格、纯ASCII字符词条、拼音词条，也会出现在这个文件中（用于充分的对照）。需要人工解决这些冲突，添加到Translation.txt或blacklist.opencc.txt中。\n")
        for line in difference_sort:
            f2.write(line + '\n') 
            word = line.split('\t',2)[0].strip()
            if not word in skiplist:
                f.write(line + '\n') 

    # 根据值排序字典，保存opencc配置文件
    sorted_dict = OrderedDict(sorted(dictionary.items(), key=lambda x: x[1]))
    n = 0

    with open(f"scripts/wiki.opencc.txt", 'w') as output_file, open(f"scripts/wiki2.opencc.txt", 'w') as output_file2:
        output_file2.write("# wiki2.opencc.txt 被剔除的其他字形-简中词条对应表，按简中词条排序。主要剔除了有括号、有空格、纯ASCII字符词条、拼音词条。在Translation.txt和blacklist.opencc.txt中出现的词条不会出现在这个文件中。这些词条基本不会进入输入法候选词，因此基本不会过杀，输出此文件仅供后续检查。\n")
        
        # 创建 OpenCC 转换器实例
        converter1 = opencc.OpenCC('t2s.json')  # 繁体转简体
        converter2 = opencc.OpenCC('tw2s.json')  # 台湾正体转大陆简体
        converter3 = opencc.OpenCC('hk2s.json')  # 香港字形转大陆简体
        
        for key, value in sorted_dict.items():
            if  key in skiplist:
                continue
            elif '(' in value or '（' in value or any(char.isspace() for char in key) or any(char.isspace() for char in value) or all(ord(c) < 128 for c in key) or all(ord(c) < 128 for c in value) or re.match(pinyin_pattern, key) or re.match(pinyin_pattern, value):
                output_file2.write(key+"\t"+value + '\n')
            elif any(char.isdigit() for char in value) ^  any(char.isdigit() for char in key):
                # 避免转换字形前后其一有数字，另一无数字
                output_file2.write(key+"\t"+value + '\n')
            else :
                # 不存储与默认转换字形结果相同的词条
                # if converter1.convert(key) != value and  converter2.convert(key) != value and  converter3.convert(key) != value :
                if converter1.convert(key) != value:
                    output_file.write(key+"\t"+value + '\n')
                    n+=1


    print(f'Write OpenCC: {n}/{len(dictionary)}')
if __name__ == "__main__":
    main()
