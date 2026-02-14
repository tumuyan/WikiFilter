// WikiFilter.cpp : 此文件包含 "main" 函数。程序执行将在此处开始并结束。
//
// 在C / C++中，数组下标的类型是std::size_t，因此数组的大小首先不能超过size_t所能表示的大小。
// 这个数据类型是在库文件stdio.h中通过typedef声明的，对于32位程序它被定义为unsighed int，对于64位程序定义为unsigned long。
// 前者能表示的最大大小为2 ^ 32 - 1，后者为2 ^ 64 - 1。
// 也就是说，32位程序最大处理4G文件

// 优化版本：使用 Aho-Corasick 自动机进行多模式匹配
// 支持分批处理大规模词典，内存可控

#include <regex>
#include <vector>
#include <sstream>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <iostream>
#include <fstream>
#include <cstring>
#include <unordered_map>
#include <unordered_set>
#include <queue>
#include <memory>
#include <iomanip>

using namespace std;

// ============================================================================
// Aho-Corasick 自动机实现
// ============================================================================

struct ACNode {
    unordered_map<char, ACNode*> children;
    ACNode* fail = nullptr;
    vector<int> output;  // 存储匹配词条的索引

    ~ACNode() {
        for (auto& pair : children) {
            delete pair.second;
        }
    }
};

class AhoCorasick {
private:
    ACNode* root;
    int patternCount;

public:
    AhoCorasick() : root(new ACNode()), patternCount(0) {}

    ~AhoCorasick() {
        delete root;
    }

    // 添加词条
    void insert(const string& pattern, int index) {
        ACNode* current = root;
        for (char c : pattern) {
            if (current->children.find(c) == current->children.end()) {
                current->children[c] = new ACNode();
            }
            current = current->children[c];
        }
        current->output.push_back(index);
        patternCount++;
    }

    // 构建失败指针（BFS）
    void buildFailureLinks() {
        queue<ACNode*> q;

        // 根节点的子节点失败指针指向根
        for (auto& pair : root->children) {
            pair.second->fail = root;
            q.push(pair.second);
        }

        // BFS 构建失败指针
        while (!q.empty()) {
            ACNode* current = q.front();
            q.pop();

            for (auto& pair : current->children) {
                char c = pair.first;
                ACNode* child = pair.second;
                ACNode* fail = current->fail;

                // 查找失败指针
                while (fail != nullptr && fail->children.find(c) == fail->children.end()) {
                    fail = fail->fail;
                }

                if (fail == nullptr) {
                    child->fail = root;
                } else {
                    child->fail = fail->children[c];
                    // 合并输出
                    if (!child->fail->output.empty()) {
                        child->output.insert(child->output.end(),
                            child->fail->output.begin(), child->fail->output.end());
                    }
                }
                q.push(child);
            }
        }
    }

    // 搜索文本，返回所有匹配的词条索引（去重）
    unordered_set<int> search(const char* text, size_t length) {
        unordered_set<int> matches;
        ACNode* current = root;

        for (size_t i = 0; i < length; i++) {
            char c = text[i];

            // 沿着失败指针查找
            while (current != root && current->children.find(c) == current->children.end()) {
                current = current->fail;
            }

            if (current->children.find(c) != current->children.end()) {
                current = current->children[c];
            } else {
                current = root;
            }

            // 收集匹配
            if (!current->output.empty()) {
                matches.insert(current->output.begin(), current->output.end());
            }
        }

        return matches;
    }

    int getPatternCount() const { return patternCount; }
};

// ============================================================================
// 全局变量
// ============================================================================

mutex file_mutex;
mutex cout_mutex;

// 批次处理的词条范围
struct BatchRange {
    size_t start;
    size_t end;
};

// ============================================================================
// 使用 AC 自动机处理一个批次的词条
// ============================================================================

void process_batch_with_ac(
    const vector<string>& words,
    const BatchRange& range,
    char** line_ptr,
    const vector<size_t>& line_lengths,
    size_t line_size,
    const string& output_path,
    int batch_id,
    int total_batches)
{
    auto batch_start = chrono::high_resolution_clock::now();

    // 1. 构建 AC 自动机
    AhoCorasick ac;
    for (size_t i = range.start; i < range.end; i++) {
        ac.insert(words[i], i - range.start);
    }
    ac.buildFailureLinks();

    // 2. 为本批次词条创建计数器
    vector<atomic<int>> line_counts(range.end - range.start);
    for (auto& count : line_counts) {
        count = 0;
    }

    // 3. 扫描所有行
    auto scan_start = chrono::high_resolution_clock::now();
    chrono::duration<double> ac_build_time = scan_start - batch_start;  // AC构建时间
    auto last_log_time = scan_start;
    size_t last_log_lines = 0;  // 上次日志输出时的行数
    const int LOG_INTERVAL_SECONDS = 60;  // 每 60 秒输出一次进度日志
    const size_t LOG_CHECK_INTERVAL = 5000;  // 每 5000 行检查一次时间

    // 首次打印：显示AC构建时间
    {
        lock_guard<mutex> lock(cout_mutex);
        cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
             << "AC build time: " << fixed << setprecision(2) << ac_build_time.count() << "s"
             << ", words: " << (range.end - range.start)
             << ", starting scan..." << endl;
    }

    for (size_t line_idx = 0; line_idx < line_size; line_idx++) {
        const char* line_text = line_ptr[line_idx];
        size_t line_len = line_lengths[line_idx];

        if (line_len == 0) continue;

        // 获取本行匹配的所有词条
        unordered_set<int> matches = ac.search(line_text, line_len);

        // 计数（每行最多计1次）
        for (int idx : matches) {
            line_counts[idx]++;
        }

        // 定期检查是否需要输出日志
        if ((line_idx + 1) % LOG_CHECK_INTERVAL == 0) {
            auto current_time = chrono::high_resolution_clock::now();
            chrono::duration<double> elapsed_since_last_log = current_time - last_log_time;

            if (elapsed_since_last_log.count() >= LOG_INTERVAL_SECONDS) {
                chrono::duration<double> scan_elapsed = current_time - scan_start;  // 扫描时间（不含AC构建）
                double progress = (line_idx + 1) * 100.0 / line_size;
                double avg_lines_per_sec = (line_idx + 1) / scan_elapsed.count();  // 累计平均速度
                double instant_lines_per_sec = (line_idx + 1 - last_log_lines) / elapsed_since_last_log.count();  // 瞬时速度

                {
                    lock_guard<mutex> lock(cout_mutex);
                    cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
                         << fixed << setprecision(1) << progress << "%"
                         << " (" << (line_idx + 1) << "/" << line_size << " lines)"
                         << ", avg: " << setprecision(0) << avg_lines_per_sec << " lines/s"
                         << ", instant: " << instant_lines_per_sec << " lines/s"
                         << ", scan: " << setprecision(1) << scan_elapsed.count() << "s"
                         << endl;
                }
                last_log_time = current_time;
                last_log_lines = line_idx + 1;
            }
        }
    }

    // 4. 输出结果
    stringstream ss;
    int match_count = 0;
    for (size_t i = range.start; i < range.end; i++) {
        int count = line_counts[i - range.start].load();
        if (count > 0) {
            ss << words[i] << "\t" << count << "\n";
            match_count++;
        }
    }

    // 5. 写入文件
    {
        lock_guard<mutex> lock(file_mutex);
        ofstream file(output_path, ios::app);
        if (file.is_open()) {
            file << ss.str();
            file.close();
        }
    }

    auto batch_end = chrono::high_resolution_clock::now();
    chrono::duration<double> scan_duration = batch_end - scan_start;

    {
        lock_guard<mutex> lock(cout_mutex);
        cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
             << "words: " << (range.end - range.start)
             << ", matched: " << match_count
             << ", AC build: " << fixed << setprecision(2) << ac_build_time.count() << "s"
             << ", scan: " << scan_duration.count() << "s" << endl;
    }
}

// ============================================================================
// 处理文件（主处理逻辑）
// ============================================================================

static int process_files(const string& raw_path, const string& txt_path, int num_threads) {
    auto total_start = chrono::high_resolution_clock::now();

    // 1. 打开文件
    ifstream raw_file(raw_path, ios::binary | ios::ate);
    ifstream txt_file(txt_path);
    const string output_path = raw_path + ".filted.csv";

    // 清空输出文件
    {
        ofstream output_file(output_path, ios_base::out);
        output_file.close();
    }

    // 设置 UTF-8 locale
    const char* utf8_locales[] = {
        "en_US.UTF-8", "en_US.utf8", "en_GB.UTF-8", "en_GB.utf8",
        "C.UTF-8", "C.utf8", "POSIX.UTF-8",
        "zh_CN.UTF-8", "zh_CN.utf8", "zh_TW.UTF-8", "zh_TW.utf8",
        "zh_HK.UTF-8", "zh_HK.utf8", "zh_SG.UTF-8", "zh_SG.utf8",
        "ja_JP.UTF-8", "ja_JP.utf8",
        "ko_KR.UTF-8", "ko_KR.utf8",
        nullptr
    };
    bool locale_set = false;
    for (int i = 0; utf8_locales[i] != nullptr; ++i) {
        try {
            locale utf8_loc(utf8_locales[i]);
            txt_file.imbue(utf8_loc);
            raw_file.imbue(utf8_loc);
            locale_set = true;
            break;
        } catch (const std::runtime_error& e) {
            continue;
        }
    }
    if (!locale_set) {
        cerr << "Warning: No UTF-8 locale available, using classic locale" << endl;
    }

    if (!raw_file.is_open() || !txt_file.is_open()) {
        cerr << "Error opening file: " << raw_path << endl;
        return -1;
    }

    // 2. 读取文本文件到内存
    streamsize size = raw_file.tellg();
    raw_file.seekg(0, ios::beg);

    cout << "Loading text file: " << raw_path << " (" << size << " bytes)" << endl;

    char* raw = new char[size + 1];
    raw[size] = '\0';
    if (!raw_file.read(raw, size)) {
        cerr << "Error reading file: " << raw_path << endl;
        delete[] raw;
        return -2;
    }
    raw_file.close();

    // 3. 分行处理
    vector<unsigned long> line;
    vector<size_t> line_lengths;  // 预计算每行长度
    line.push_back(0);
    for (unsigned long i = 0; i < size; i++) {
        if (raw[i] == '\n') {
            // 计算当前行长度（不含换行符）
            size_t line_start = line.back();
            line_lengths.push_back(i - line_start);
            line.push_back(i);
            raw[i] = '\0';
        }
    }
    // 处理最后一行（如果没有以换行符结尾）
    if (raw[size - 1] != '\n') {
        line_lengths.push_back(size - line.back());
        line.push_back(size + 1);
    }

    size_t line_size = line.size() - 1;

    // 创建行指针数组
    char** line_ptr = new char*[line_size];
    line_ptr[0] = raw;
    for (size_t i = 1; i < line_size; i++) {
        line_ptr[i] = raw + line[i] + 1;
    }

    cout << "Text file lines: " << line_size << endl;

    // 4. 读取词典
    string word;
    regex pattern("\\s+");
    vector<string> words;
    while (getline(txt_file, word)) {
        word = regex_replace(word, pattern, "");
        if (word.length() > 1) {
            words.push_back(word);
        }
    }
    txt_file.close();

    cout << "Dictionary size: " << words.size() << " words" << endl;

    // 5. 动态分批处理策略
    // 根据词条数量和线程数动态计算批次大小
    size_t total_words = words.size();

    // 内存估算参数
    // - 每个 Trie 节点约 60 字节
    // - 每个词条平均 4 字符，约 4 个节点
    // - 目标：每批 AC 自动机内存控制在 ~128MB
    const size_t TARGET_MEMORY_MB = 128;
    const size_t EST_BYTES_PER_WORD = 240;  // 约 4 节点 * 60 字节
    const size_t MAX_WORDS_PER_BATCH = (TARGET_MEMORY_MB * 1024 * 1024) / EST_BYTES_PER_WORD;

    // 计算批次数量
    // 策略：批次数至少是线程数的 3 倍（更好的负载均衡）
    // 同时控制每批内存不超过限制
    size_t min_batches_for_load_balance = (size_t)num_threads * 3;
    size_t max_batches_by_memory = (total_words + 1000 - 1) / 1000;  // 至少 1000 词/批
    size_t batches_by_memory_limit = (total_words + MAX_WORDS_PER_BATCH - 1) / MAX_WORDS_PER_BATCH;

    size_t num_batches = max(min_batches_for_load_balance,
                             min(batches_by_memory_limit, max_batches_by_memory));
    num_batches = max(num_batches, (size_t)1);  // 至少 1 批

    // 根据批次数计算每批词条数
    size_t words_per_batch = (total_words + num_batches - 1) / num_batches;

    // 估算每批内存
    size_t estimated_mem_per_batch_mb = (words_per_batch * EST_BYTES_PER_WORD) / (1024 * 1024);

    cout << "Dictionary size: " << total_words << " words" << endl;
    cout << "Batch strategy: " << num_batches << " batches, "
         << words_per_batch << " words/batch (max)" << endl;
    cout << "Estimated memory per batch: ~" << estimated_mem_per_batch_mb << " MB" << endl;
    cout << "Using " << num_threads << " threads" << endl;

    // 6. 多线程并行处理批次
    vector<BatchRange> batches;
    for (size_t i = 0; i < num_batches; i++) {
        BatchRange range;
        range.start = i * words_per_batch;
        range.end = min((i + 1) * words_per_batch, total_words);
        if (range.start >= total_words) break;
        batches.push_back(range);
    }
    num_batches = batches.size();  // 更新实际批次数

    // 使用线程池处理批次
    atomic<size_t> next_batch(0);

    auto worker = [&]() {
        while (true) {
            size_t batch_idx = next_batch.fetch_add(1);
            if (batch_idx >= num_batches) break;

            process_batch_with_ac(
                words,
                batches[batch_idx],
                line_ptr,
                line_lengths,
                line_size,
                output_path,
                batch_idx,
                num_batches
            );
        }
    };

    vector<thread> threads;
    for (int i = 0; i < num_threads; i++) {
        threads.emplace_back(worker);
    }

    for (auto& t : threads) {
        t.join();
    }

    // 7. 清理
    delete[] raw;
    delete[] line_ptr;

    auto total_end = chrono::high_resolution_clock::now();
    chrono::duration<double> total_duration = total_end - total_start;

    cout << "========================================" << endl;
    cout << "Completed in " << total_duration.count() << " seconds" << endl;
    cout << "Output: " << output_path << endl;

    return 0;
}

// ============================================================================
// 主函数
// ============================================================================

int main(int argc, char* argv[]) {
    if (argc < 3) {
        cout << "用法: " << argv[0] << " <dict file path> <text file path> [thread number]" << endl;
        cout << endl;
        cout << "优化版本：使用 Aho-Corasick 自动机进行多模式匹配" << endl;
        cout << "支持大规模词典（百万级）和大型文本文件（GB级）" << endl;
        return 1;
    }

    string dict_path = argv[1];
    string text_path = argv[2];
    int num_threads = 1;

    if (argc > 3) {
        num_threads = atoi(argv[3]);
    } else {
        num_threads = thread::hardware_concurrency();
        if (num_threads > 64) {
            // 线程数太大，可能在容器中获得了物理机的核心数
            cerr << "threads " << num_threads << " -> 2" << endl;
            num_threads = 2;
        }
    }

    if (num_threads <= 0) {
        cerr << "threads 0 -> 1" << endl;
        num_threads = 1;
    } else {
        cout << "threads = " << num_threads << endl;
    }

    return process_files(text_path, dict_path, num_threads);
}
