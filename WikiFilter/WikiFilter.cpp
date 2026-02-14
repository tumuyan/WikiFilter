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
#include <sys/sysinfo.h>  // 获取系统内存信息

using namespace std;

// ============================================================================
// 从文件读取数值（用于 cgroup 内存信息）
// ============================================================================
static size_t read_cgroup_value(const char* path) {
    FILE* file = fopen(path, "r");
    if (!file) return 0;
    size_t value = 0;
    if (fscanf(file, "%zu", &value) != 1) {
        fclose(file);
        return 0;
    }
    fclose(file);
    return value;
}

// ============================================================================
// 获取系统可用内存（单位：MB）
// 兼容 Docker/cgroup 环境
// ============================================================================
static size_t get_available_memory_mb() {
    // 1. 获取物理机内存信息
    struct sysinfo info;
    size_t host_available_mb = 1024;  // 默认 1GB
    if (sysinfo(&info) == 0) {
        size_t free_mb = (info.freeram * info.mem_unit) / (1024 * 1024);
        size_t buffer_mb = (info.bufferram * info.mem_unit) / (1024 * 1024);
        host_available_mb = free_mb + buffer_mb;
    }

    // 2. 尝试读取 cgroup v2 内存限制
    size_t cgroup_limit = read_cgroup_value("/sys/fs/cgroup/memory.max");
    
    // 3. 尝试读取 cgroup v1 内存限制
    if (cgroup_limit == 0) {
        cgroup_limit = read_cgroup_value("/sys/fs/cgroup/memory/memory.limit_in_bytes");
    }

    // 4. 如果没有 cgroup 限制，或者限制过大（接近物理机内存），使用物理机可用内存
    size_t host_total_mb = (info.totalram * info.mem_unit) / (1024 * 1024);
    
    if (cgroup_limit == 0 || cgroup_limit > info.totalram * info.mem_unit) {
        // 没有 cgroup 限制或限制等于/大于物理机内存
        return host_available_mb;
    }

    // 5. 有 cgroup 限制，计算容器内可用内存
    size_t cgroup_limit_mb = cgroup_limit / (1024 * 1024);
    
    // 尝试读取当前 cgroup 内存使用量
    size_t cgroup_usage = read_cgroup_value("/sys/fs/cgroup/memory.current");
    if (cgroup_usage == 0) {
        cgroup_usage = read_cgroup_value("/sys/fs/cgroup/memory/memory.usage_in_bytes");
    }
    
    size_t cgroup_usage_mb = cgroup_usage / (1024 * 1024);
    size_t cgroup_available_mb = 0;
    
    if (cgroup_limit_mb > cgroup_usage_mb) {
        cgroup_available_mb = cgroup_limit_mb - cgroup_usage_mb;
    }

    // 6. 返回 cgroup 可用内存和物理机可用内存中较小的一个
    return min(cgroup_available_mb, host_available_mb);
}

// ============================================================================
// 获取当前进程内存占用（单位：MB）
// ============================================================================
static size_t get_process_memory_mb() {
    FILE* file = fopen("/proc/self/status", "r");
    if (!file) return 0;
    char line[128];
    while (fgets(line, 128, file) != nullptr) {
        if (strncmp(line, "VmRSS:", 6) == 0) {
            fclose(file);
            return atoi(line + 6) / 1024;  // KB -> MB
        }
    }
    fclose(file);
    return 0;
}

// ============================================================================
// Aho-Corasick 自动机实现（内存优化版）
// 使用连续内存存储节点，用数组索引替代指针
// ============================================================================

// 紧凑的 AC 节点：使用 vector<pair<char,int>> 替代 unordered_map
// 子节点按字符排序，支持二分查找
struct CompactACNode {
    vector<pair<char, int>> children;  // (字符, 子节点索引)，按字符排序
    int fail = 0;                       // 失败指针（节点索引）
    int output_start = -1;              // output 在全局数组中的起始位置，-1 表示无输出
    int output_count = 0;               // output 数量
};

class AhoCorasick {
private:
    vector<CompactACNode> nodes;       // 所有节点存储在连续内存中
    vector<int> outputs;               // 所有 output 存储在连续数组中
    int patternCount;

    // 在子节点中二分查找字符
    int findChild(int nodeIdx, char c) const {
        const auto& children = nodes[nodeIdx].children;
        // 二分查找
        int left = 0, right = (int)children.size() - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (children[mid].first == c) {
                return children[mid].second;
            } else if (children[mid].first < c) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;  // 未找到
    }

    // 添加子节点（保持有序）
    int addChild(int nodeIdx, char c) {
        int newIdx = (int)nodes.size();
        nodes.push_back(CompactACNode());

        auto& children = nodes[nodeIdx].children;
        // 找到插入位置
        auto it = lower_bound(children.begin(), children.end(), make_pair(c, 0),
            [](const pair<char,int>& a, const pair<char,int>& b) {
                return a.first < b.first;
            });
        children.insert(it, make_pair(c, newIdx));
        return newIdx;
    }

public:
    AhoCorasick() : patternCount(0) {
        nodes.reserve(1000000);  // 预分配空间
        nodes.push_back(CompactACNode());  // 根节点
    }

    // 添加词条
    void insert(const string& pattern, int index) {
        int current = 0;  // 从根节点开始
        for (char c : pattern) {
            int childIdx = findChild(current, c);
            if (childIdx == -1) {
                childIdx = addChild(current, c);
            }
            current = childIdx;
        }
        // 添加输出
        if (nodes[current].output_start == -1) {
            nodes[current].output_start = (int)outputs.size();
        }
        outputs.push_back(index);
        nodes[current].output_count++;
        patternCount++;
    }

    // 构建失败指针（BFS）
    void buildFailureLinks() {
        queue<int> q;  // 存储节点索引

        // 根节点的子节点失败指针指向根
        for (const auto& child : nodes[0].children) {
            nodes[child.second].fail = 0;
            q.push(child.second);
        }

        // BFS 构建失败指针
        while (!q.empty()) {
            int current = q.front();
            q.pop();

            for (const auto& childPair : nodes[current].children) {
                char c = childPair.first;
                int child = childPair.second;
                int fail = nodes[current].fail;

                // 沿着失败指针查找
                while (fail != 0 && findChild(fail, c) == -1) {
                    fail = nodes[fail].fail;
                }

                int failChild = findChild(fail, c);
                if (fail == 0 && failChild == -1) {
                    nodes[child].fail = 0;
                } else if (failChild != -1) {
                    nodes[child].fail = failChild;
                    // 合并输出
                    if (nodes[failChild].output_count > 0) {
                        // 需要扩容 output
                        int new_start = (int)outputs.size();
                        // 复制原有 output
                        for (int i = 0; i < nodes[child].output_count; i++) {
                            outputs.push_back(outputs[nodes[child].output_start + i]);
                        }
                        // 添加 fail 节点的 output
                        for (int i = 0; i < nodes[failChild].output_count; i++) {
                            outputs.push_back(outputs[nodes[failChild].output_start + i]);
                        }
                        nodes[child].output_start = new_start;
                        nodes[child].output_count += nodes[failChild].output_count;
                    }
                } else {
                    nodes[child].fail = 0;
                }
                q.push(child);
            }
        }
    }

    // 搜索文本，返回所有匹配的词条索引（去重）
    unordered_set<int> search(const char* text, size_t length) {
        unordered_set<int> matches;
        int current = 0;  // 从根节点开始

        for (size_t i = 0; i < length; i++) {
            char c = text[i];

            // 沿着失败指针查找
            while (current != 0 && findChild(current, c) == -1) {
                current = nodes[current].fail;
            }

            int child = findChild(current, c);
            if (child != -1) {
                current = child;
            } else {
                current = 0;
            }

            // 收集匹配
            if (nodes[current].output_count > 0) {
                for (int j = 0; j < nodes[current].output_count; j++) {
                    matches.insert(outputs[nodes[current].output_start + j]);
                }
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

    size_t mem_before_ac = get_process_memory_mb();

    // 1. 构建 AC 自动机
    AhoCorasick ac;
    for (size_t i = range.start; i < range.end; i++) {
        ac.insert(words[i], i - range.start);
    }
    ac.buildFailureLinks();

    size_t mem_after_ac = get_process_memory_mb();

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
    const int LOG_INTERVAL_SECONDS = 30;  // 每 30 秒输出一次进度日志
    const size_t LOG_CHECK_INTERVAL = 5000;  // 每 5000 行检查一次时间

    // 首次打印：显示AC构建时间和内存
    {
        lock_guard<mutex> lock(cout_mutex);
        cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
             << "AC build time: " << fixed << setprecision(2) << ac_build_time.count() << "s"
             << ", words: " << (range.end - range.start)
             << ", MEM: " << mem_after_ac << " MB"
             << " (+" << (mem_after_ac - mem_before_ac) << " MB for AC)"
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
                chrono::duration<double> scan_elapsed = current_time - scan_start;
                double progress = (line_idx + 1) * 100.0 / line_size;
                double instant_lines_per_sec = (line_idx + 1 - last_log_lines) / elapsed_since_last_log.count();
                double avg_lines_per_sec = (line_idx + 1) / scan_elapsed.count();
                
                // ETA
                size_t remaining_lines = line_size - (line_idx + 1);
                double eta_seconds = remaining_lines / avg_lines_per_sec;
                int eta_m = (int)(eta_seconds / 60);
                int eta_s = (int)(eta_seconds) % 60;

                {
                    lock_guard<mutex> lock(cout_mutex);
                    cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
                         << fixed << setfill(' ') << setw(5) << setprecision(1) << progress << "%"
                         << " | " << setfill('0') << setw(2) << (int)(scan_elapsed.count()/60) << ":" << setw(2) << (int)scan_elapsed.count()%60
                         << ", ETA " << setw(2) << eta_m << ":" << setw(2) << eta_s
                         << " | " << setprecision(0) << (line_idx + 1)/1000 << "K/" << line_size/1000 << "K"
                         << " | " << setprecision(1) << instant_lines_per_sec/1000 << "K/s"
                         << ", Avg " << avg_lines_per_sec/1000 << "K/s"
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
    cout << "[MEM] After loading text file: " << get_process_memory_mb() << " MB" << endl;

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
    cout << "[MEM] After loading dictionary: " << get_process_memory_mb() << " MB" << endl;

    // 5. 动态分批处理策略
    // 根据可用内存动态计算批次大小
    size_t total_words = words.size();

    // 内存估算参数（优化版 CompactACNode）
    // - 每个节点约 48 字节（vector<pair> + 3个int + vector开销）
    // - 每个词条平均约 4 字符，考虑共享前缀，平均约 3 个节点
    // - 实测：214万词条 -> 986 MB，约 483 字节/词条
    // - 预估：每词条约 500 字节（保守估计）
    const size_t EST_BYTES_PER_WORD = 500;  // 基于实测数据

    // 获取系统可用内存
    size_t available_mem_mb = get_available_memory_mb();
    cout << "Available memory: " << available_mem_mb << " MB" << endl;

    // 预留内存给文件数据（2.1GB）和其他开销
    // 文件已加载到内存，占用了约 2100 MB
    const size_t FILE_DATA_MB = 2200;  // 文件数据 + line_ptr + line_lengths
    const size_t RESERVE_MB = 500;      // 其他开销预留

    // 计算可用于 AC 自动机的内存
    size_t usable_mem_mb = 0;
    if (available_mem_mb > FILE_DATA_MB + RESERVE_MB) {
        usable_mem_mb = available_mem_mb - FILE_DATA_MB - RESERVE_MB;
    } else {
        // 可用内存不足，使用保守值
        usable_mem_mb = 512;  // 默认 512MB 用于 AC 自动机
    }

    // 计算单个 AC 自动机最多能容纳多少词条
    size_t max_words_per_ac = (usable_mem_mb * 1024 * 1024) / EST_BYTES_PER_WORD;

    // 根据线程数和内存计算批次
    size_t num_batches;
    size_t words_per_batch;

    if (num_threads == 1) {
        // 单线程模式：构建尽可能大的 AC 自动机，减少扫描次数
        if (total_words <= max_words_per_ac) {
            // 所有词条可以放入单个 AC 自动机
            num_batches = 1;
            words_per_batch = total_words;
            cout << "Single-thread mode: All words fit in one AC automaton" << endl;
        } else {
            // 需要分批，但每批尽可能大
            num_batches = (total_words + max_words_per_ac - 1) / max_words_per_ac;
            words_per_batch = (total_words + num_batches - 1) / num_batches;
            cout << "Single-thread mode: Split into " << num_batches << " batches" << endl;
        }
    } else {
        // 多线程模式：批次数至少是线程数的 3 倍（更好的负载均衡）
        size_t min_batches_for_load_balance = (size_t)num_threads * 3;
        size_t batches_by_memory = (total_words + max_words_per_ac - 1) / max_words_per_ac;
        num_batches = max(min_batches_for_load_balance, batches_by_memory);
        num_batches = max(num_batches, (size_t)1);
        words_per_batch = (total_words + num_batches - 1) / num_batches;
    }

    // 估算每批内存
    size_t estimated_mem_per_batch_mb = (words_per_batch * EST_BYTES_PER_WORD) / (1024 * 1024);

    cout << "Dictionary size: " << total_words << " words" << endl;
    cout << "Batch strategy: " << num_batches << " batches, "
         << words_per_batch << " words/batch (max)" << endl;
    cout << "Estimated memory per batch: ~" << estimated_mem_per_batch_mb << " MB" << endl;
    cout << "Using " << num_threads << " thread(s)" << endl;

    // 6. 批次处理
    vector<BatchRange> batches;
    for (size_t i = 0; i < num_batches; i++) {
        BatchRange range;
        range.start = i * words_per_batch;
        range.end = min((i + 1) * words_per_batch, total_words);
        if (range.start >= total_words) break;
        batches.push_back(range);
    }
    num_batches = batches.size();  // 更新实际批次数

    if (num_threads == 1) {
        // 单线程模式：顺序处理，减少缓存热身开销
        for (size_t batch_idx = 0; batch_idx < num_batches; batch_idx++) {
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
    } else {
        // 多线程模式：使用线程池处理批次
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
