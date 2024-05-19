# Wiki Filter
本仓库包含了一系列工具的源码、数据以及CI脚本，用于从维基百科的全文备份验证指定词条列表文件的出现频率，从而获得输入法的高质量词条。

## 为什么
大量非常用词条出现在候选列表中是一件非常令人不爽的事情。我称之为“废词”。  
如果直接把维基百科的词条列表作为一个词库，就会引入大量废词。  
那么如何减少废词呢？我之前给出的答案是使用正则、黑名单、白名单以及根据经验构建的一系列算法来过滤废词。  
但是产生的效果是有限的；因此我又使用了新的理论：使用词频去筛选低频词条。  

那么应该如何筛选呢？我有两个基本思路：1. 使用搜索引擎检索词条，结合返回的总页数、前N页缩略内容精确匹配到完整词条的比例，判断这个词条是否是常用词条。 2. 使用维基百科全文来验证这些词条。
由于搜索引擎对访问频率有限制，所以方式1不可行，那么就需要实践方式2了。

考虑到1个词条出现在10篇文章中各出现1次，要远比在1篇文章中出现10次重要，因此我选择了统计每个词条出现在多少篇文章中的统计方式。

## 怎么做
以下简述了人工和CI所做的事情
1. 人工半自动预处理维基词条标题，上传到仓库 280万->48万
2. CI获取维基全文xml （12G）
3. CI运行WikiExtract，从xml提取全文 （2.5G）
4. CI运行本仓库one_line.py脚本，合并每篇以`<doc></doc>`包裹的xml内容为每行一篇纯文本，处理过程清除一部分无效文本，并从中提取形如`{H|zh-cn:计算机; zh-sg:电脑; zh-tw:電腦;}`的内容为字典。  
5. CI并行运行任务，编译本仓库C++代码，获得WikiFilter工具，使用维基全文验证指定词条列表，输出词频为csv文件
6. 使用merge_csv.py合并多个csv的数据为一个文件
7. 使用OpenCC处理词频文件，再次使用merge_csv.py合并词频，从而叠加简繁词频统计；根据阈值输出合格词条。

## 结果呢
目前数据保存于ci的Artifacts中。包含：
1. opencc 从维基全文获取的opencc格式的其他语言到简体中文的转换列表
2. wiki_??.csv 使用维基全文分片文件验证的词频
3. wiki_result_*_1 合并后的词频文件
4. wiki_result__all 处理后的全部文件
5. wiki_result_chs_dict  高于阈值的纯简中词条

## 仓库结构
- WikiFilter/WikiFilter.cpp 统计词频的C++源码
- scripts/one_line.py 把WikiExtract结果处理为每篇内容为一行，同时输出其他语言-简中的opencc的配置文件
- scripts/merge_csv.py 把多个csv文件合并为1个，同时输出无词频的txt文件（可根据阈值剔除词频低于一定值的词条）
- scripts/blacklist.opencc.txt 输出opencc配置文件时，如词条在词文件中出现，则跳过
- scripts/Translation.txt 预设的opencc数据文件，精选其他语言-简中
- scripts/a2s.json 预设的opencc配置文件，其他语言-简中，包含Translation.txt
- scripts/a2s2.json 预设的opencc配置文件，其他语言-简中，包含Translation.txt和wiki.opencc.txt

