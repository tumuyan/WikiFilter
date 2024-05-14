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
#include <thread>
#include <mutex>
#include <chrono>
#include <iostream>
using namespace std;

std::mutex file_mutex;
std::atomic<int> a; // 第几次分配任务

void writeToFile(const std::string& data, int numWrites, const std::string& path) {
	file_mutex.lock();
	std::ofstream file(path, std::ios::app); // 以追加模式打开文件
	if (file.is_open()) {
		for (int i = 0; i < numWrites; i++) {
			file << data << std::endl;
		}
		file.close();
	}
	file_mutex.unlock();
}

 int process_words(std::vector<string> words, int i,int BATCH_SIZE, char** line_ptr, int LINE_SIZE, string output_path) {

	int r = 0;
	int  b = 1;
	int n = 0;
	auto start = std::chrono::high_resolution_clock::now();
	auto begin = std::chrono::high_resolution_clock::now();

	std::stringstream ss;

	for (int j = BATCH_SIZE * i; j < words.size();j++) {
		string word = words[j];
		const size_t w_size = word.size();
		char* w = const_cast<char*>(word.data());

		int k = 0;
		int loop = 0;
		for (int loop = 0; loop < LINE_SIZE; loop++) {
			if (strstr(line_ptr[loop], w) != NULL)
				k++;
		}

		//for (int loop = 0; loop < LINE_SIZE - 1; loop++) {
		//	char* pos = line_ptr[loop+1];
		//	if (memmem(line_ptr[loop], pos- line_ptr[loop], w, w_size) != NULL)
		//		k++;
		//}

		if (k > 0)
		{
			r++;
			ss << word << "\t" << k << "\n";
		}
		b++;
		n++;

		if (b == BATCH_SIZE || j==words.size()-1) {
			auto end = std::chrono::high_resolution_clock::now();
			std::chrono::duration<double> duration = end - start;
			std::chrono::duration<double> duration2 = end - begin;
			std::cout << "Thread[" << i <<"] " << n << "\tBatch time: " << duration.count() << ", Total time: " << duration2.count() << ", Avg " << n / duration2.count() << " it/s" << std::endl;
			start = std::chrono::high_resolution_clock::now();

			file_mutex.lock();
			std::ofstream file(output_path, std::ios::app); // 以追加模式打开文件
			if (file.is_open()) {
				file << ss.str();
				file.close();
			}

			j = BATCH_SIZE * (a.load())-1;
			a.fetch_add(1);

			file_mutex.unlock();

			ss.clear();
			b = 1;
		}

	}
	return r;
}

static int process_files(const std::string& raw_path, const std::string& txt_path, const bool print_result) {
	std::ifstream raw_file(raw_path, std::ios::binary | std::ios::ate);
	std::ifstream txt_file(txt_path);
	std::ofstream output_file(raw_path + ".filted.csv",ios_base::out);
	output_file.close();
	// 设置文件编码为 UTF-8
	txt_file.imbue(std::locale("en_US.UTF-8"));
	raw_file.imbue(std::locale("en_US.UTF-8"));

	if (!raw_file.is_open() || !txt_file.is_open()) {
		std::cerr << "Error opening file! "  << std::endl;
		return -1;
	}

	std::streamsize size = raw_file.tellg();
	raw_file.seekg(0, std::ios::beg);

    char* raw = new char[size+1];
	raw[size] = '0';
	if (!raw_file.read(raw, size)) {
		std::cerr << "Error reading file! " << std::endl;
		return -2;
	}

	// 数据集分行
	std::vector<unsigned long> line;
	line.push_back(0);
	for (unsigned long i = 0; i < size; i++) {
		if (raw[i] == '\n') {
			line.push_back(i);
			raw[i] = '\0';
		}
	}
	if (raw[size] != '\0')
		line.push_back(size + 1);

	// 定义一个整数偏移量列表
	size_t LINE_SIZE = line.size();
	// 分配内存,创建一个指针数组
	char** line_ptr = (char**)malloc(LINE_SIZE * sizeof(char*));

	// 将整数偏移量转换为指针
	line_ptr[0] = raw;
	for (int i = 1; i < LINE_SIZE; i++) {
		line_ptr[i] = raw + line[i]+1;
	}
	LINE_SIZE--;

	// 读取词库文件
	std::string word;
	std::regex pattern("\\s+");
	std::vector<std::string> words;
	while (std::getline(txt_file, word)) {
		word = std::regex_replace(word, pattern, "");
		if(word.length()>1)// 跳过单字
			words.push_back(word); 
	}

	// 获取硬件支持的并发线程数
	 int num_threads = std::thread::hardware_concurrency();
	if (num_threads == 0) {
	    num_threads = 1; // 默认使用一个线程
	    std::cerr << "threads 0 -> 1" << std::endl;
	}
	else if (num_threads >= 16) {
	    num_threads = 2; // 虚拟环境检测到的核心数量可能不等于被分配的数量
	    std::cerr << "threads " << num_threads << " -> 1" << std::endl;
	}
	else {
	    std::cout << "threads =" << num_threads << std::endl;
	}

	// 设置批的大小
	 int batch_size = 500;
	if (num_threads * batch_size > words.size())
		batch_size =int( words.size() / num_threads) + 1;

	std::thread* th=new std::thread[num_threads];

	a.store(num_threads);
	for ( int i = 0; i < num_threads; i++) {
		th[i] = thread(process_words, words, i, batch_size, line_ptr, LINE_SIZE, raw_path + ".filted.csv");
	}
	for ( int i = 0; i < num_threads; i++) {
		th[i].join();
	}

	delete[] raw;
	free(line_ptr);
	raw_file.close();
	txt_file.close();
	return 0;
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
		//std::cout << "text file math " << r << " words, path: " << argv[2] << std::endl;
        if (r<1)
            return r-1000;
	}
	else {
	for (int i = 2; i < argc; i++) {
		int r = process_files(argv[i], param1, false);
		//std::cout << "text file " << i - 1 << " math " << r << " words, path: " << argv[i] << std::endl;
	}
	}



	return 0;
}
