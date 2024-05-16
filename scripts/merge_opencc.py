import sys
import os
import re

# 逐行读取指定文件。每行都形如：
# {H|zh-cn:计算机; zh-sg:电脑; zh-tw:電腦;}
# 将其转换为 其他语言\t简中\n 形式的opencc文件

class Translation:
    # 定义正则表达式模式为类属性
    PATTERN = r'(zh-hans|zh-cn):([^;]+)'

    def __init__(self):
        # 将解析结果保存在类内
        self.dictionary = {}
        self.lines = []

    def read_file(self, file_path):
        """
        逐行读取文件并将每行内容存储为字符串列表。
        """
        self.lines = []
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self.lines = [line.strip()[1:-1].replace("H|","") for line in file]
        except FileNotFoundError:
            print(f"Error: {file_path} not found.")
        except IOError:
            print(f"Error: Unable to read {file_path}.")
        return self.lines

    def split_strings(self):
        
        for string in strings:
            # 捕获简中关键字
            match = re.search(self.PATTERN, string)
            if match:
                key = match.group(2)
                if len(key) >= 2:
                    # 遍历各个区域
                    locales = string.split(';')
                    if len(locales) > 1:
                        for locale in locales:
                            if len(locale) >= 2:
                                parts = locale.split(':', 1)
                                if len(parts) == 2:
                                    lang, value = parts
                                    if key != value:
                                        self.dictionary[value] = key
                            # else:
                            #     print(f"Warning: Skipping locale with length < 2: {locale}")
                    else:
                        print(f"Warning: Skipping string with < 2 locales: {string}")
                # else:
                #     print(f"Warning: Skipping key with length < 2: {key}")
            # else:
            #     print(f"Warning: Unable to parse localization string: {string}")
        return self.dictionary

    def print_content(self):
        """
        遍历每个字符串数组,并打印出非空的内容。
        """
        for key, value in self.dictionary.items():
            print(f"{key}\t{value}")

    def save_content(self, path):
        try:
            with open(path, "w") as file:
                for key, value in self.dictionary.items():
                    file.write(f"{key}\t{value}\n")
                print("save fininsh")
        except IOError:
            print(f"Error: Unable to write to {path}.")
        

# # 示例用法
# file_path = 'text/AA/wiki_00_translate.txt'
# translation = Translation()
# strings = translation.read_file(file_path)
# translation.split_strings()
# # translation.print_content()
# translation.save_content('text/AA/wiki_00_cc.txt')



def merge_opencc(input_folder, path,input_suffix):
    # 获取 input_folder 目录中的所有 txt 文件
    csv_files = [f for f in os.listdir(input_folder) if f.endswith(input_suffix)]

    # 创建一个字典来存储 key 和其对应的值
    PATTERN = r'(zh-hans|zh-cn):([^;]+)'
    dictionary = {}

    for csv_file in csv_files:
        print(csv_file)
        with open(f'{input_folder}/{csv_file}', 'r') as f:
            for line in f:
                string = line.strip()[1:-1].replace("H|","")

                # 捕获简中关键字
                match = re.search(PATTERN, string)
                if match:
                    key = match.group(2)
                    if len(key) >= 2 and len(key)<=30:
                        # 遍历各个区域
                        locales = string.split(';')
                        if len(locales) > 1:
                            for locale in locales:
                                if len(locale) >= 2:
                                    parts = locale.split(':', 1)
                                    if len(parts) == 2:
                                        lang, value = parts
                                        if key != value:
                                            dictionary[value] = key
                                # else:
                                #     print(f"Warning: Skipping locale with length < 2: {locale}")
                        else:
                            print(f"Warning: Skipping string with < 2 locales: {string}")

    try:
        with open(path, "w") as file:
            for key, value in dictionary.items():
                file.write(f"{key}\t{value}\n")
            print("save fininsh")
    except IOError:
        print(f"Error: Unable to write to {path}.")


def main():
    if len(sys.argv) < 3:
        print("Usage: python merge_opencc.py <input folder> <output path> <input suffix filter> ")
        print("  input folder: \t扫描目录的路径")
        print("  output path: \t输出文件的路径")
        print("  input suffix filter: \t输入文件的文件名过滤器，只处理与之匹配的文件，默认.translation.txt")
        return
    input_suffix = '.translation.txt'
    if len(sys.argv) >3:
        input_suffix = sys.argv[3]

    merge_opencc(sys.argv[1],sys.argv[2],input_suffix)

if __name__ == "__main__":
    main()
