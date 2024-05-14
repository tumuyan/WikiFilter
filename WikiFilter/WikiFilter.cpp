// WikiFilter.cpp : 此文件包含 "main" 函数。程序执行将在此处开始并结束。
//
// 在C / C++中，数组下标的类型是std::size_t，因此数组的大小首先不能超过size_t所能表示的大小。
// 这个数据类型是在库文件stdio.h中通过typedef声明的，对于32位程序它被定义为unsighed int，对于64位程序定义为unsigned long。
// 前者能表示的最大大小为2 ^ 32 - 1，后者为2 ^ 64 - 1。

// 也就是说，32位程序最大处理4G文件

#include <regex>
#include <vector>
#include <sstream>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <iostream>
#include <fstream>

using namespace std;

mutex file_mutex;
atomic_int a = 0;; // 第几次分配任务

 int process_words(vector<string> words, int i,int BATCH_SIZE, char** line_ptr, int LINE_SIZE, string output_path) {

	int r = 0;
	int  b = 1;
	int n = 1;
	auto start = chrono::high_resolution_clock::now();
	auto begin = chrono::high_resolution_clock::now();

	stringstream ss;

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
			auto end = chrono::high_resolution_clock::now();
			chrono::duration<double> duration = end - start;
			chrono::duration<double> duration2 = end - begin;
			cout << "Thread[" << i <<"] " << n << "\tBatch time: " << duration.count() << ", Total time: " << duration2.count() << ", Avg " << n / duration2.count() << " it/s" << endl;
			start = chrono::high_resolution_clock::now();

			file_mutex.lock();
			ofstream file(output_path, ios::app); // 以追加模式打开文件
			if (file.is_open()) {
				file << ss.str();
				file.close();
			}

			j = BATCH_SIZE * a-1;
			a++;

			file_mutex.unlock();

			ss.clear();
			b = 1;
		}

	}
	return r;
}

static int process_files(const string& raw_path, const string& txt_path, int num_threads) {
	ifstream raw_file(raw_path, ios::binary | ios::ate);
	ifstream txt_file(txt_path);
	ofstream output_file(raw_path + ".filted.csv",ios_base::out);
	output_file.close();
	// 设置文件编码为 UTF-8
	txt_file.imbue(locale("en_US.UTF-8"));
	raw_file.imbue(locale("en_US.UTF-8"));

	if (!raw_file.is_open() || !txt_file.is_open()) {
		cerr << "Error opening file! "  << endl;
		return -1;
	}

	streamsize size = raw_file.tellg();
	raw_file.seekg(0, ios::beg);

    char* raw = new char[size+1];
	raw[size] = '0';
	if (!raw_file.read(raw, size)) {
		cerr << "Error reading file! " << endl;
		return -2;
	}

	// 数据集分行
	vector<unsigned long> line;
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

	cout << "text file lines = " << LINE_SIZE << ", " << raw_path << endl;

	// 读取词库文件
	string word;
	regex pattern("\\s+");
	vector<string> words;
	while (getline(txt_file, word)) {
		word = regex_replace(word, pattern, "");
		if(word.length()>1)// 跳过单字
			words.push_back(word); 
	}

	cout << "dict file lines = " << words.size() << ", " << txt_path << endl;


	// 设置批的大小
	 int batch_size = 500;
	if (num_threads * batch_size > words.size())
		batch_size =int( words.size() / num_threads) + 1;


	thread* th = new thread[num_threads];

	a = num_threads;
	for (int i = 0; i < num_threads; i++) {
		th[i] = thread(process_words, words, i, batch_size, line_ptr, LINE_SIZE, raw_path + ".filted.csv");
	}
	for (int i = 0; i < num_threads; i++) {
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
		cout << "用法: " << argv[0] << " <dict file path> <text file path> [thread number]" << endl;
		return 1;
	}

	// 获取参数
	string param1 = argv[1];
	int r = 0;


	// 获取硬件支持的并发线程数
	int num_threads = 1;
	if (argc > 3) {
		num_threads = atoi(argv[3]);
	}
	else {
		num_threads = thread::hardware_concurrency();
		if (num_threads >= 16) {
			num_threads = 2; // 虚拟环境检测到的核心数量可能不等于被分配的数量
			cerr << "threads " << num_threads << " -> 2" << endl;
		}
	}
	if (num_threads == 0) {
		num_threads = 1; // 默认使用一个线程
		cerr << "threads 0 -> 1" << endl;
	}
	cout << "threads = " << num_threads << endl;
	return process_files(argv[2], param1, num_threads);


}
