"""
Wiki词条处理共用模块
"""
import re


def remove_punctuation_length(text):
    """计算去除标点后的文本长度"""
    punctuation_pattern = r'[\u3000-\u303F\uFF00-\uFFEF\u2000-\u206F\u0021-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E]'
    cleaned_text = re.sub(punctuation_pattern, '', text)
    return len(cleaned_text)


def split_article(text, return_matches=False):
    """
    将长字符串分为符合正则表达式"{[^{}\[\]=]+zh[^{}\[\]=]+}"的多个片段,
    从中提取形如{H|zh-cn:计算机; zh-sg:电脑; zh-tw:電腦;}的内容为字典。

    参数:
    text (str): 要分割的长字符串
    return_matches (bool): 是否返回原始匹配信息
    
    返回:
    默认返回: (dictionary, text, difference)
    当 return_matches=True 时返回: (dictionary, text, difference, matches_list)
        - dictionary: 其他语言-简中字典
        - text: 替换后的文本
        - difference: 存在冲突的内容集合
        - matches_list: [(原始片段, {key: value, ...}), ...] 原始匹配信息
    """
    pattern = r'\{[^\{\}\[\]\=]+zh[^\{\}\[\]\=]+\}'
    matches = re.findall(pattern, text)
    
    PATTERN = r'(zh-hans|zh-cn):([^;]+)'
    dictionary = {}
    keys = []
    clips = []
    difference = set()
    matches_list = []  # 存储原始匹配信息
    
    for line in matches:
        if len(line) > line.count(';') * 64:
            continue
        string = line.strip()[1:-1].strip()
        
        parts = string.split('|', 1)
        if len(parts) == 2:
            prefix = parts[0].strip()
            remainder = parts[1].strip()
            if prefix in "*HhAa-":
                string = remainder
            elif prefix in remainder:
                string = remainder
            elif ':' not in prefix and len(prefix) >= 2:
                string = "unknow:" + prefix + ';' + remainder
        if len(string) >= 2 and string[0] in "*HhAa-" and string[1] in " |":
            string = string[2:]
        elif string.startswith("|"):
            string = string[1:]
        match = re.search(PATTERN, string)
        if match:
            key = match.group(2).strip()
            if remove_punctuation_length(key) >= 2 and len(key) <= 30 and any(ord(c) >= 128 for c in key):
                locales = string.split(';')
                if len(locales) == 1:
                    locales = string.split()
                if len(locales) > 1:
                    recorded = False
                    local_dict = {}  # 当前片段的词条映射
                    for locale in locales:
                        if len(locale) >= 2:
                            parts = locale.split(':', 1)
                            if len(parts) == 2:
                                lang, value = parts
                                lang = lang.strip()
                                if not re.match(r'^[a-zA-Z][a-zA-Z-]*$', lang):
                                    print(f"Warning: Invalid lang '{lang}' in {repr(string)}, length {len(string)}")
                                    continue
                                value = value.strip()
                                if value in "重定向;重新導向":
                                    continue
                                if key != value and len(value) >= 2 and len(value) <= 30:
                                    local_dict[value] = key
                                    if value in dictionary:
                                        if key != dictionary[value]:
                                            difference.add(value + "\t" + key)
                                            difference.add(value + "\t" + dictionary[value])
                                    else:
                                        dictionary[value] = key
                                    if not recorded:
                                        clips.append(line)
                                        keys.append(key)
                                        recorded = True
                    if return_matches and local_dict:
                        matches_list.append((line, local_dict))
                else:
                    print(f"Warning: Skipping string with < 2 locales: {repr(string)}")

    for i in range(len(keys)):
        text = text.replace(clips[i], keys[i])

    if return_matches:
        return dictionary, text, difference, matches_list
    return dictionary, text, difference
