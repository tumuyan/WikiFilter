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
// 全局常量
// ============================================================================
// 内存估算参数：实测214万词条 -> 986 MB，约 483 字节/词条
// 预估：每词条约 500 字节（保守估计）
const size_t EST_BYTES_PER_WORD = 500;

// ============================================================================
// 全局变量
// ============================================================================
// 批次处理前的基准内存（用于计算AC内存增量）
static atomic<size_t> g_base_memory_mb(0);

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
    // 优化：使用vector收集+排序去重，比unordered_set快2-3倍
    vector<int> search(const char* text, size_t length) {
        vector<int> matches;
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
                    matches.push_back(outputs[nodes[current].output_start + j]);
                }
            }
        }

        // 去重：排序后去重
        if (matches.size() > 1) {
            sort(matches.begin(), matches.end());
            matches.erase(unique(matches.begin(), matches.end()), matches.end());
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

// 分块边界信息（不存储数据，只存储偏移）
struct ChunkBoundary {
    size_t start_offset;    // 分块在文件中的起始偏移
    size_t end_offset;      // 分块在文件中的结束偏移
    size_t line_count;      // 该分块的行数
};

// 流式文件加载器 - 真正的内存优化版本
// 只保持一个分块在内存中，或缓存整个文件（当内存足够时）
class StreamingFileLoader {
private:
    string file_path;
    size_t chunk_size;
    size_t total_lines;
    size_t file_size;
    vector<ChunkBoundary> boundaries;  // 分块边界信息
    vector<char> cached_file;          // 缓存的整个文件内容（当文件能完全加载时）
    bool file_cached;                  // 是否已缓存整个文件

public:
    StreamingFileLoader(const string& path, size_t chunk_bytes = 200 * 1024 * 1024)
        : file_path(path), chunk_size(chunk_bytes), total_lines(0), file_size(0), file_cached(false) {}

    // 预扫描文件，记录分块边界（不加载内容到内存）
    bool scanBoundaries() {
        ifstream file(file_path, ios::binary);
        if (!file.is_open()) {
            cerr << "Error opening file: " << file_path << endl;
            return false;
        }

        // 获取文件大小
        file.seekg(0, ios::end);
        file_size = file.tellg();
        file.seekg(0, ios::beg);

        cout << "Scanning file: " << file_path << " (" << file_size << " bytes)" << endl;

        // 预分配缓冲区用于扫描
        vector<char> buffer(min(chunk_size, file_size) + 1);
        size_t current_offset = 0;
        size_t chunk_id = 0;

        while (current_offset < file_size) {
            size_t read_size = min(chunk_size, file_size - current_offset);
            file.read(buffer.data(), read_size);
            size_t actual_read = file.gcount();

            if (actual_read == 0) break;

            // 如果不是最后一块，找到最后一个换行符
            size_t chunk_end = actual_read;
            if (current_offset + actual_read < file_size) {
                for (int i = actual_read - 1; i >= 0; i--) {
                    if (buffer[i] == '\n') {
                        chunk_end = i + 1;
                        break;
                    }
                }
            }

            // 统计该分块的行数
            size_t lines = 0;
            for (size_t i = 0; i < chunk_end; i++) {
                if (buffer[i] == '\n') lines++;
            }

            // 记录边界信息
            ChunkBoundary boundary;
            boundary.start_offset = current_offset;
            boundary.end_offset = current_offset + chunk_end;
            boundary.line_count = lines;
            boundaries.push_back(boundary);

            total_lines += lines;
            chunk_id++;

            cout << "  Chunk " << chunk_id << ": "
                 << chunk_end / (1024 * 1024) << " MB, "
                 << lines << " lines" << endl;

            // 移动到下一个分块
            current_offset = current_offset + chunk_end;
            file.seekg(current_offset, ios::beg);
        }

        file.close();
        cout << "Total lines: " << total_lines << ", chunks: " << boundaries.size() << endl;
        return true;
    }

    // 获取总行数
    size_t getLineCount() const { return total_lines; }

    // 获取分块数量
    size_t getChunkCount() const { return boundaries.size(); }

    // 流式处理所有行（每个分块处理完后释放内存）
    void streamProcess(function<bool(const char*, size_t, size_t, size_t)> callback) {
        // 如果文件已缓存，从缓存读取
        if (file_cached && !cached_file.empty()) {
            size_t processed_lines = 0;
            size_t chunk_idx = 0;
            char* data = cached_file.data();
            size_t chunk_bytes = file_size;

            // 处理每一行
            size_t line_start = 0;
            for (size_t i = 0; i < chunk_bytes; i++) {
                if (data[i] == '\n') {
                    data[i] = '\0';
                    size_t line_len = i - line_start;

                    if (line_len > 0) {
                        if (!callback(data + line_start, line_len, chunk_idx, processed_lines)) {
                            return;
                        }
                    }

                    processed_lines++;
                    line_start = i + 1;
                }
            }
            return;
        }

        // 从文件读取（原逻辑）
        ifstream file(file_path, ios::binary);
        if (!file.is_open()) {
            cerr << "Error reopening file: " << file_path << endl;
            return;
        }

        size_t processed_lines = 0;

        for (size_t chunk_idx = 0; chunk_idx < boundaries.size(); chunk_idx++) {
            const auto& boundary = boundaries[chunk_idx];
            size_t chunk_bytes = boundary.end_offset - boundary.start_offset;

            // 只为当前分块分配内存
            vector<char> buffer(chunk_bytes + 1);

            // 读取当前分块
            file.seekg(boundary.start_offset, ios::beg);
            file.read(buffer.data(), chunk_bytes);
            buffer[chunk_bytes] = '\0';

            // 处理每一行
            size_t line_start = 0;
            for (size_t i = 0; i < chunk_bytes; i++) {
                if (buffer[i] == '\n') {
                    buffer[i] = '\0';
                    size_t line_len = i - line_start;

                    if (line_len > 0) {
                        if (!callback(buffer.data() + line_start, line_len, chunk_idx, processed_lines)) {
                            return;  // 停止处理
                        }
                    }

                    processed_lines++;
                    line_start = i + 1;
                }
            }

            // buffer 在循环结束后自动释放，内存被回收
        }

        file.close();
    }

    // 获取单个分块的内存占用估算
    size_t getChunkMemoryMB() const {
        if (boundaries.empty()) return 0;
        size_t max_chunk = 0;
        for (const auto& b : boundaries) {
            size_t chunk_size = b.end_offset - b.start_offset;
            if (chunk_size > max_chunk) max_chunk = chunk_size;
        }
        return max_chunk / (1024 * 1024);
    }

    // 缓存整个文件到内存（当只有1个chunk时调用）
    bool cacheEntireFile() {
        if (boundaries.size() != 1) {
            return false;  // 只缓存单chunk文件
        }

        ifstream file(file_path, ios::binary);
        if (!file.is_open()) {
            cerr << "Error opening file for caching: " << file_path << endl;
            return false;
        }

        cached_file.resize(file_size + 1);
        file.read(cached_file.data(), file_size);
        cached_file[file_size] = '\0';
        file.close();

        file_cached = true;
        cout << "File cached in memory (" << file_size / (1024 * 1024) << " MB)" << endl;
        return true;
    }

    // 检查文件是否已缓存
    bool isFileCached() const { return file_cached; }
};

// ============================================================================
// 使用 AC 自动机处理一个批次的词条（使用分块加载器）
// ============================================================================

void process_batch_with_ac(
    const vector<string>& words,
    const BatchRange& range,
    StreamingFileLoader& file_loader,
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

    // 3. 流式扫描所有行（每个分块处理完后释放内存）
    auto scan_start = chrono::high_resolution_clock::now();
    chrono::duration<double> ac_build_time = scan_start - batch_start;  // AC构建时间
    auto last_log_time = scan_start;
    size_t lines_processed = 0;  // 已处理的行数
    size_t lines_at_last_log = 0;  // 上次日志时的行数（用于计算瞬时速度）
    const int LOG_INTERVAL_SECONDS = 30;  // 每 30 秒输出一次进度日志
    const size_t LOG_CHECK_INTERVAL = 5000;  // 每 5000 行检查一次时间

    size_t total_lines = file_loader.getLineCount();  // 获取总行数

    // 首次打印：显示AC构建时间和内存
    {
        lock_guard<mutex> lock(cout_mutex);
        size_t process_mem_mb = get_process_memory_mb();
        size_t base_mem_mb = g_base_memory_mb.load();
        size_t ac_total_mb = (process_mem_mb > base_mem_mb) ? (process_mem_mb - base_mem_mb) : 0;
        cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
             << "AC build time: " << fixed << setprecision(2) << ac_build_time.count() << "s"
             << ", words: " << (range.end - range.start)
             << ", MEM: " << process_mem_mb << " MB"
             << " (+" << ac_total_mb << " MB for all AC)"
             << ", starting scan..." << endl;
    }

    // 使用流式处理遍历所有行
    file_loader.streamProcess([&](const char* line_text, size_t line_len, size_t chunk_idx, size_t global_line) -> bool {
        if (line_len == 0) return true;

        // 获取本行匹配的所有词条
        vector<int> matches = ac.search(line_text, line_len);

        // 计数（每行最多计1次）
        for (int idx : matches) {
            line_counts[idx]++;
        }

        lines_processed++;

        // 定期检查是否需要输出日志
        if (lines_processed % LOG_CHECK_INTERVAL == 0) {
            auto current_time = chrono::high_resolution_clock::now();
            chrono::duration<double> elapsed_since_last_log = current_time - last_log_time;

            if (elapsed_since_last_log.count() >= LOG_INTERVAL_SECONDS) {
                chrono::duration<double> scan_elapsed = current_time - scan_start;
                double progress = lines_processed * 100.0 / total_lines;
                double instant_lines_per_sec = (lines_processed - lines_at_last_log) / elapsed_since_last_log.count();
                double avg_lines_per_sec = lines_processed / scan_elapsed.count();

                // ETA
                size_t remaining_lines = total_lines - lines_processed;
                double eta_seconds = remaining_lines / avg_lines_per_sec;
                int eta_m = (int)(eta_seconds / 60);
                int eta_s = (int)eta_seconds % 60;

                {
                    lock_guard<mutex> lock(cout_mutex);
                    cout << "Batch[" << batch_id + 1 << "/" << total_batches << "] "
                         << fixed << setfill(' ') << setw(5) << setprecision(1) << progress << "%"
                         << " | " << setfill('0') << setw(2) << (int)(scan_elapsed.count()/60) << ":" << setw(2) << (int)scan_elapsed.count()%60
                         << ", ETA " << setw(2) << eta_m << ":" << setw(2) << eta_s
                         << " | " << setprecision(0) << lines_processed/1000 << "K/" << total_lines/1000 << "K"
                         << " | " << setprecision(1) << instant_lines_per_sec/1000 << "K/s"
                         << ", Avg " << avg_lines_per_sec/1000 << "K/s"
                         << endl;
                }
                last_log_time = current_time;
                lines_at_last_log = lines_processed;
            }
        }

        return true;  // 继续处理
    });

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

    // ========================================================================
    // 第一步：读取词典（先获知词条数量，才能准确预估内存需求）
    // ========================================================================
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
            locale_set = true;
            break;
        } catch (const std::runtime_error& e) {
            continue;
        }
    }
    if (!locale_set) {
        cerr << "Warning: No UTF-8 locale available, using classic locale" << endl;
    }

    if (!txt_file.is_open()) {
        cerr << "Error opening file: " << txt_path << endl;
        return -1;
    }

    // 读取词典
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

    size_t total_words = words.size();
    cout << "Dictionary size: " << total_words << " words" << endl;
    cout << "[MEM] After loading dictionary: " << get_process_memory_mb() << " MB" << endl;

    // ========================================================================
    // 第二步：内存规划（根据词条数预估 AC 自动机内存，剩余给 chunk）
    // ========================================================================

    const size_t RESERVE_MB = 300;  // 预留给系统和其他开销
    
    // 获取系统可用内存
    size_t available_mem_mb = get_available_memory_mb();
    cout << "Available memory: " << available_mem_mb << " MB" << endl;
    
    // 预估 AC 自动机所需内存
    size_t estimated_ac_mem_mb = (total_words * EST_BYTES_PER_WORD) / (1024 * 1024);
    cout << "Estimated AC memory: " << estimated_ac_mem_mb << " MB" << endl;
    
    // 计算可用于 chunk 的内存 = 总可用 - AC预估 - 预留
    size_t available_for_chunk_mb = 0;
    if (available_mem_mb > estimated_ac_mem_mb + RESERVE_MB) {
        available_for_chunk_mb = available_mem_mb - estimated_ac_mem_mb - RESERVE_MB;
    }
    
    // ========================================================================
    // 第三步：先获取文件大小，再确定 chunk 大小
    // ========================================================================
    
    // 获取文件大小
    size_t file_size = 0;
    {
        ifstream file(raw_path, ios::binary | ios::ate);
        if (!file.is_open()) {
            cerr << "Error opening file: " << raw_path << endl;
            return -1;
        }
        file_size = file.tellg();
        file.close();
    }
    size_t file_size_mb = file_size / (1024 * 1024);
    cout << "Input file size: " << file_size_mb << " MB" << endl;
    
    // 设置 chunk 大小（使用 80% 的可用 chunk 内存，留 20% 缓冲）
    const size_t MIN_CHUNK_MB = 50;
    size_t chunk_mb = (size_t)(available_for_chunk_mb * 0.8);
    chunk_mb = max(MIN_CHUNK_MB, chunk_mb);
    
    // 如果文件大小小于可用chunk内存，直接使用文件大小作为chunk大小
    // 这样可以一次性加载整个文件到内存
    if (file_size_mb <= available_for_chunk_mb && file_size_mb > 0) {
        chunk_mb = file_size_mb + 1;  // +1 确保边界情况
        cout << "File fits in available memory, loading entire file as single chunk" << endl;
    }
    
    cout << "Memory plan: AC=" << estimated_ac_mem_mb << "MB, Reserve=" << RESERVE_MB 
         << "MB, Chunk=" << chunk_mb << "MB (available: " << available_for_chunk_mb << "MB)" << endl;
    
    size_t chunk_size = chunk_mb * 1024 * 1024;

    // ========================================================================
    // 第四步：扫描文件分块边界（不加载内容到内存）
    // ========================================================================
    StreamingFileLoader file_loader(raw_path, chunk_size);
    if (!file_loader.scanBoundaries()) {
        cerr << "Error scanning file: " << raw_path << endl;
        return -1;
    }

    cout << "[MEM] After scanning file: " << get_process_memory_mb() << " MB" << endl;
    cout << "[StreamingFileLoader] chunk size: " << file_loader.getChunkMemoryMB() << " MB" << endl;

    // 如果只有1个chunk（文件能完全加载），缓存整个文件避免重复IO
    if (file_loader.getChunkCount() == 1) {
        file_loader.cacheEntireFile();
        cout << "[MEM] After caching file: " << get_process_memory_mb() << " MB" << endl;
    }

    // ========================================================================
    // 第五步：计算批次策略
    // ========================================================================
    
    // 计算可用于 AC 自动机的内存（实际值，基于当前可用内存）
    size_t current_available_mb = get_available_memory_mb();
    size_t usable_mem_mb = 0;
    if (current_available_mb > file_loader.getChunkMemoryMB() + RESERVE_MB) {
        usable_mem_mb = current_available_mb - file_loader.getChunkMemoryMB() - RESERVE_MB;
    } else {
        usable_mem_mb = 512;  // 保守值
    }

    // 计算单个 AC 自动机最多能容纳多少词条
    size_t max_words_per_ac = (usable_mem_mb * 1024 * 1024) / EST_BYTES_PER_WORD;

    // 根据线程数和内存计算批次
    size_t num_batches;
    size_t words_per_batch;

    if (num_threads == 1) {
        // 单线程模式：构建尽可能大的 AC 自动机，减少扫描次数
        if (total_words <= max_words_per_ac) {
            num_batches = 1;
            words_per_batch = total_words;
            cout << "Single-thread mode: All words fit in one AC automaton" << endl;
        } else {
            num_batches = (total_words + max_words_per_ac - 1) / max_words_per_ac;
            words_per_batch = (total_words + num_batches - 1) / num_batches;
            cout << "Single-thread mode: Split into " << num_batches << " batches" << endl;
        }
    } else {
        // 多线程模式：根据内存限制计算批次数，确保至少等于线程数
        size_t batches_by_memory = (total_words + max_words_per_ac - 1) / max_words_per_ac;
        num_batches = max(batches_by_memory, (size_t)num_threads);
        words_per_batch = (total_words + num_batches - 1) / num_batches;
    }

    // 估算每批内存
    size_t estimated_mem_per_batch_mb = (words_per_batch * EST_BYTES_PER_WORD) / (1024 * 1024);

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
        // 记录基准内存
        g_base_memory_mb.store(get_process_memory_mb());
        
        for (size_t batch_idx = 0; batch_idx < num_batches; batch_idx++) {
            process_batch_with_ac(
                words,
                batches[batch_idx],
                file_loader,
                output_path,
                batch_idx,
                num_batches
            );
        }
    } else {
        // 多线程模式：使用线程池处理批次
        // 记录基准内存（所有batch开始前的内存）
        g_base_memory_mb.store(get_process_memory_mb());
        
        atomic<size_t> next_batch(0);

        auto worker = [&]() {
            while (true) {
                size_t batch_idx = next_batch.fetch_add(1);
                if (batch_idx >= num_batches) break;

                process_batch_with_ac(
                    words,
                    batches[batch_idx],
                    file_loader,
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

    // 7. 清理（ChunkedFileLoader 会自动在析构时释放内存）

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
    }

    if (num_threads <= 0) {
        // 线程数为 0 时，自动设置为硬件并发数
        num_threads = thread::hardware_concurrency();
        if (num_threads > 64) {
            // 线程数太大，可能在容器中获得了物理机的核心数
            cerr << "Auto threads " << num_threads << " -> 2" << endl;
            num_threads = 2;
        }
        cout << "Auto-detected threads = " << num_threads << endl;
    } else {
        cout << "threads = " << num_threads << endl;
    }

    return process_files(text_path, dict_path, num_threads);
}
