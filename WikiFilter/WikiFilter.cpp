// WikiFilter.cpp : 此文件包含 "main" 函数。程序执行将在此处开始并结束。
//
// 在C / C++中，数组下标的类型是std::size_t，因此数组的大小首先不能超过size_t所能表示的大小。
// 这个数据类型是在库文件stdio.h中通过typedef声明的，对于32位程序它被定义为unsighed int，对于64位程序定义为unsigned long。
// 前者能表示的最大大小为2 ^ 32 - 1，后者为2 ^ 64 - 1。

// 也就是说，32位程序最大处理4G文件
#include <iostream>


#include <regex>
#include <fstream>
#include <vector>
#include <sstream>

#include <chrono>

#define DEBUG false;
static int process_files(const std::string& raw_path, const std::string& txt_path, const bool print_result) {
	std::ifstream raw_file(raw_path, std::ios::binary | std::ios::ate);
	std::ifstream txt_file(txt_path);
	std::ofstream output_file(raw_path + ".filted.csv");
	// 设置文件编码为 UTF-8
	raw_file.imbue(std::locale("en_US.UTF-8"));
	txt_file.imbue(std::locale("en_US.UTF-8"));
	raw_file.imbue(std::locale("en_US.UTF-8"));

	if (!raw_file.is_open() || !txt_file.is_open() || !output_file.is_open()) {
		std::cerr << "Error opening file!" << std::endl;
		return 0;
	}

	std::streamsize size = raw_file.tellg();
	raw_file.seekg(0, std::ios::beg);

    char* raw = new char[size];
	if (!raw_file.read(raw, size)) {
		std::cerr << "Error reading file!" << std::endl;
		return 0;
	}

	std::vector<unsigned long> line;
	for (unsigned long i = 0; i < size; ++i) {
		if (raw[i] == '\n') {
			line.push_back(i);
		}
	}

	std::string word;
	int r = 0;
	std::regex pattern("\\s+");

	int  b = 0;
	auto start = std::chrono::high_resolution_clock::now();
	auto begin = std::chrono::high_resolution_clock::now();


	while (std::getline(txt_file, word)) {
		word = std::regex_replace(word, pattern, "");
		if (word.size() < 1)
			continue;
		const int w_size = word.size();
		char* w = const_cast<char*>(word.data());

		int k = 0;
		size_t pos = 0;
		int l = 0;

		while (pos < size) {

			if (raw[pos] == w[0]) {
				//char sub_array[w_size +1]; // 存储子数组
				//std::copy(pos + 5, input + 10, sub_array); // 从索引 5 到 9 复制
				//sub_array[5] = '\0'; // 手动添加结尾空字符


				int j = 1;
				for (; j < word.size(); j++) {
					{
						if (raw[pos + j] != w[j])
							break;
					}
				}
				if (j == word.size()) {
					k++;
					while (pos > line[l]) {
						l++;
					}
					pos = line[l];

				}
			}
			pos++;

		}


		if (k > 0)
		{
			r++;
			if (print_result)
			{
					std::cout << "-" << word << "-" << k << std::endl;
			}

		output_file << word << "\t" << k << "\n";
		}

		b++;
		if (b % 1000 == 0) {
			auto end = std::chrono::high_resolution_clock::now();

			std::chrono::duration<double> duration = end - start;
			std::chrono::duration<double> duration2=  end - begin;
			std::cout << "Match " << b <<", Time: " << duration.count() << ", Total " << duration2.count() << ", " << b/ duration2.count() << " it/s" << std::endl;
			start = std::chrono::high_resolution_clock::now();

		}

	}

	delete[] raw;
	raw_file.close();
	txt_file.close();
	output_file.close();
	return r;
}



int main(int argc, char* argv[]) {
	// 检查命令行参数的数量
	if (argc < 3) {
		std::cout << "用法: " << argv[0] << " <dict file path> <text file path>" << std::endl;
		return 1;
	}

	// 获取参数

	std::string param1 = argv[1];

	// 打印参数
	//std::cout << "dict file path: " << param1 << std::endl;
	//for (int i = 2; i < argc; i++) {
	//	std::cout << "dict file path[" << i - 1 << "]: " << argv[i] << std::endl;
	//}

	//	std::cout << "Matching file..." << std::endl;

	// bool single_input = (argc == 3);
	if (argc == 3) {
		int r = process_files(argv[2], param1, false);
		std::cout << "text file math " << r << " words, path: " << argv[2] << std::endl;
	}
	else {
	for (int i = 2; i < argc; i++) {
		int r = process_files(argv[i], param1, false);
		std::cout << "text file " << i - 1 << " math " << r << " words, path: " << argv[i] << std::endl;
	}
	}



	return 0;
}
