# Wiki Filter
本仓库包含了一系列工具的源码、数据以及CI脚本，用于从维基百科的全文备份验证指定词条列表文件的出现频率，从而获得输入法的高质量词条。

## 为什么
大量非常用词条出现在候选列表中是一件非常令人不爽的事情。我称之为"废词"。  
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
4. CI运行本仓库 one_line.py脚本，合并每篇以`<doc></doc>`包裹的xml内容为每行一篇纯文本，处理过程清除一部分无效文本，并从中提取形如`{H|zh-cn:计算机; zh-sg:电脑; zh-tw:電腦;}`的内容为字典。  
5. CI并行运行任务，编译本仓库C++代码，获得WikiFilter工具，使用维基全文验证指定词条列表，输出词频为csv文件
6. 使用`merge_csv.py`合并多个csv的数据为一个文件
7. 使用OpenCC处理词频文件，再次使用`merge_csv.py`合并词频，从而叠加简繁词频统计；根据阈值输出合格词条。作为副产物，输出`*.freq.csv`文件统计每个词频值对应多少个词条
8. 生成 Rime 输入法词库：
   - 使用 ImeWlConverterCmd 将词频文件转换为 Rime 格式的 yaml 文件
   - 使用 `optimize_dict.py` 检查并修正编码问题
   - 使用 `fix_yaml.sh` 为优化后的词库添加 Rime 头部信息

## 结果呢
目前数据保存于ci的Artifacts中。包含：
1. opencc 从维基全文获取的opencc格式的其他语言到简体中文的转换列表
2. wiki_??.csv 使用维基全文分片文件验证的词频
3. wiki_result_*_1 合并后的词频文件
4. wiki_result__all 处理后的全部文件
5. wiki_result_chs_dict  高于预设阈值的纯简中词条，**不建议直接使用。**由于目前生成的opencc并不理想，建议下载`wiki_result_*_1`从中获取未作简繁转换的`merge.csv`，通过`scripts/postprocess.bat`（其中的路径需要手动调整）对文件简繁转换、过滤词频以及其他处理。
6. rime_pinyin_dict  Rime 拼音词库（目前包含维基百科词库、萌娘百科词库、流星词库）

## 仓库结构

### 核心工具
- **WikiFilter/** — 统计词频的C++源码
  - `WikiFilter.cpp`：主程序，多线程并行过滤维基全文，统计词条在文章中的出现次数
- **scripts/** — 各类工具脚本

### 维基百科处理脚本
- `run-all.sh` — 完整处理流程一键执行：设置环境→构建→下载→提取→过滤→合并
- `setup-env.sh` — 自动安装系统依赖（wget, p7zip, ripgrep, opencc, g++, java等）和 Python 依赖
- `download-wiki.sh` — 从 Wikimedia dump 下载维基百科 XML 全文
- `download-release.sh` — 从 GitHub Release 下载预提取的维基百科内容
- `download-dict.sh` — 下载词库文件（支持 wiki 标题列表、GitHub Release、自定义 URL 三种来源）
- `extract-wiki.sh` — 使用 WikiExtractor 从 XML 提取维基百科纯文本内容
- `build-wikifilter.sh` — 编译 WikiFilter C++ 程序（g++ -O3 -pthread）
- `one_line.py` — 将 WikiExtractor 结果处理为每行一篇纯文本，同时输出其他语言→简中的 OpenCC 配置文件
- `wiki_utils.py` — 共用模块，提供文本处理（去标点长度计算、词典提取等）
- `split_file.py` — 将单行格式的维基全文切分为指定数量的分片，用于并行处理
- `merge_csv.py` — 合并多个 csv 文件的词频数据，支持阈值过滤，输出无词频的 txt 文件
- `merge_opencc.py` — 从维基全文的标签信息中提取其他语言→简中的转换数据
- `filter-wiki.sh` — 并行调用 WikiFilter 过滤指定分片
- `merge-result.sh` — 合并过滤结果并执行 OpenCC 简繁转换

### 词库解析与 Rime 词库生成
- `generate_liuxing.sh` — 自动检测架构，从 GitHub 下载 ImeWlConverterCmd 工具到 `imewlconverter/` 目录
- `process-dict.sh` — 使用 Dict-Trick（Clean.jar）对词库文件进行预清理
- `optimize_dict.py` — **Rime 词库编码优化工具**，检查并修正中英混输词条的编码格式：
  - 解析 `...` 标记后的 tab 分割词条
  - 检查词条各部分数量合法性（1-3 部分）
  - 检查权重合法性（整数、小数、百分数）
  - 编码预处理：规范化多段分隔符（多个连续分隔符合并为单个）、去除编码中的数字
  - 检查编码中英文段的正确性（`_EnglishWord`、逐字母展开等）并自动修正
  - 输出优化后的词库文件 + 分析报告
- `fix_yaml.sh` — 对优化后的 yaml 词库添加 Rime 文件头
- `dict-tick-preprocess.txt` — Dict-Trick 的清理规则配置

### OpenCC 相关文件
- `Translation.txt` — 预设的 OpenCC 数据文件，手动精选的其他语言→简中词条转换表
- `a2s.json` — OpenCC 配置文件（其他语言→简中），包含 Translation.txt
- `a2s2.json` — OpenCC 配置文件（其他语言→简中），包含 Translation.txt 和自动生成的 wiki.opencc.txt
- `blacklist.opencc.txt` — 输出 OpenCC 配置时跳过的词条（排除不必要的或错误的转换）
- `blacklist2.opencc.txt` — 容易产生歧义而不建议转换的词条
- `TSCharacters.ocd2` / `TSPhrases.ocd2` — OpenCC 字形转换数据文件

### 其他实用脚本
- `fix_yaml.sh` — 调用 optimize_dict.py 处理 yaml 词库，添加 Rime 头部
- `git_push_to_github.sh` — 推送当前分支到 GitHub 上游仓库
- `git_pull_upstream_main.sh` — 从 upstream 拉取并合并 master 分支
- `postprocess.bat` — Windows 下本地处理数据：OpenCC 简繁转换 + 词频过滤

### Skill
- `.codebuddy/skills/ime-dict-evaluator` — 评估词条可用性的 AI skill。在 CodeBuddy 中使用提示词 `评估 input.txt 的词条，结果保存到 output.csv`

## 运行过程生成的文件
- `wiki.opencc.txt` 根据维基全文的标签信息，生成的其他字形→简中词条对应表，按简中词条排序。不存储与默认简繁转换结果相同的词条。
- `wiki1.opencc.txt` 存在循环/链式引用的词条。即 key -> value -> 最终简中。这些词条虽然在wiki.opencc.txt中，但是显然质量较差。
- `wiki2.opencc.txt` 被剔除的其他字形→简中词条对应表，按简中词条排序。主要剔除了有括号、有空格、纯ASCII字符词条、拼音词条。在Translation.txt和blacklist.opencc.txt中出现的词条不会出现在这个文件中。这些词条基本不会进入输入法候选词，因此基本不会过杀，输出此文件仅供后续检查。
- `wiki3.opencc.txt` 存在冲突的内容（同词条对应了多个简中结果）在Translation.txt和blacklist.opencc.txt中出现的词条不会出现在这个文件中。即使是剔除了有括号、有空格、纯ASCII字符词条、拼音词条，也会出现在这个文件中（用于充分的对照）。需要人工解决这些冲突，添加到Translation.txt或blacklist.opencc.txt中。
- `wiki4.opencc.txt` 存在冲突的内容（同词条对应了多个简中结果）在Translation.txt和blacklist.opencc.txt中出现的词条也会出现在这个文件中。用于后期对词条重新检查。
- `filted.chs.txt` 经过词频过滤后的简体中文词条列表

## Rime 词库优化工具用法

```bash
# 仅检查编码问题，生成报告（不修改文件）
python scripts/optimize_dict.py pinyin_simp_liuxing.dict.yaml

# 检查并自动修正编码问题
python scripts/optimize_dict.py melt_eng.dict.yaml --fix

# 保留编码中的数字（默认去除数字）
python scripts/optimize_dict.py my_dict.yaml --fix --keep-digits

# 指定编码分隔符为逗号
python scripts/optimize_dict.py my_dict.yaml --delim ,

# 指定输出路径
python scripts/optimize_dict.py input.dict.yaml --fix -o output.dict.yaml -r report.txt
```
