import sys
import os
import csv
# 遍历input_folder目录中的csv文件，加总每个csv的相同key的值，保存为新的csv文件

def merge_csv(input_folder, output_filename,input_suffix,output_filter):
    # 创建一个字典来存储 key 和其对应的值
    key_counts = {}

    for root, dirs, files in os.walk(input_folder):
        for csv_file in files:
            if csv_file.endswith(input_suffix):
                print(csv_file)
                # 打开 csv 文件
                with open(f'{input_folder}/{csv_file}', 'r' , encoding='utf-8') as f:
                    for line in f:
                        
                        if '\t' in line:
                            # 获取 key 和值
                            k, value = line.split('\t')
                            v = int(value)
                            if k not in key_counts:
                                key_counts[k] = v
                            else:
                                key_counts[k] += v
                        elif len(line)>1:
                            print("Error: in line content",line )
    print("Contains", len(key_counts), "keys")
    
    if len(key_counts) <1:
        return
        
    keys = []
    count_freq = {}
    count_sum = 0
    
    # 创建一个新的 csv 文件来存储聚合后的结果
    with open( input_folder + "/"+ output_filename + ".csv" , 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # 遍历字典并写入新的 csv 文件
        for key, count in key_counts.items():
            print(key+"\t"+str(count), file=f)
            if count > output_filter:
                keys.append(key)

            if count in count_freq:
                count_freq[count] += 1
            else:
                count_freq[count] = 1

    sorted_keys  =  sorted(keys)
    with open(input_folder + "/"+ output_filename + ".txt", 'w', newline='', encoding='utf-8') as f:
        for key in sorted_keys :
            print(key, file=f)

    
    sorted_freq  =  sorted(count_freq.items())
    with open(input_folder + "/"+ output_filename + ".freq.csv", 'w', newline='', encoding='utf-8') as f:
        f.write("词频, 词条数, 累积比例\n")
        for count, freq in sorted_freq:
            # print(f'{count}\t{freq}\n')
            count_sum = count_sum + freq
            f.write(f'{count}, {freq}, {count_sum/len(key_counts)}\n')
            
    print("Output dict", len(keys), int(100*len(keys)/len(key_counts)),"%")



# 遍历文件夹，对后缀不是txt和csv的文件运行wikiextractor_xml2txt()
# 处理后打印总共处理了多少个部分，最终输出了多少个部分，比例是多少

import os
# 使用示例
# folder_path = 'text/AA'
# min_length = 100
def main():
    if len(sys.argv) < 3:
        print("Usage: python merge_csv.py <input folder> <output filename> <output value filter> <input suffix filter> ")
        print("  input folder: \t扫描目录的路径")
        print("  output filename: \t输出合并后的csv/txt文件文件名（输出时会自动增加后缀）")
        print("  output value filter: \t输出词频过滤器，设置后输出一份与之匹配的词条，默认0")
        print("  input suffix filter: \t输入文件的文件名过滤器，只处理与之匹配的文件，默认.filted.csv")
        return
    input_suffix = '.filted.csv'
    output_filter = 0
    if len(sys.argv) >3:
        output_filter = int(sys.argv[3])

        if len(sys.argv) >4:
            input_suffix = sys.argv[4]

    merge_csv(sys.argv[1],sys.argv[2],input_suffix,output_filter)

if __name__ == "__main__":
    main()
