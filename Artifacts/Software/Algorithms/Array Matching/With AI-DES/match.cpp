// ============================================================================
// AI-EES ARTIFACT: AIEES-ART-20250614-XEON-INTERSECT-0001
// Requirement:     REQ-INTENT-0001-INT-ARRAY-MATCH
// Semantics:       Set Intersection (unique common int32 values, no indices)
// Target:          Intel Xeon, in-memory arrays up to ~10^9 elements
// Algorithm:       Radix-partitioned, multi-threaded flat hash intersection
// Verification:    Golden Tests vs scalar oracle (std::set_intersection)
// Benchmark:       RFC-0009 protocol (3 warmup discarded, 10 measured runs)
// Assumptions:     Unsorted input, duplicates possible, fits in RAM (approved)
// ============================================================================
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <random>
#include <thread>
#include <vector>
#include <iterator>
namespace aiees {
// ---------------------------------------------------------------------------
// FlatSet32: open-addressing, linear-probing hash set for int32.
// Cache-friendly: single contiguous slot array, power-of-two capacity.
// INT32_MIN is the EMPTY sentinel and is tracked out-of-band for correctness
// (Golden Test boundary case: INT32_MIN must be matchable).
// ---------------------------------------------------------------------------
class FlatSet32 {
	static constexpr int32_t EMPTY = std::numeric_limits<int32_t>::min();
	std::vector<int32_t> slots_;
	std::vector<uint8_t> taken_;   // ensures each value is reported once
	size_t mask_ = 0;
	bool has_sentinel_ = false;
	bool sentinel_taken_ = false;
	static inline size_t hash(int32_t v) {    
		uint32_t x = static_cast<uint32_t>(v) * 0x9E3779B1u; // Fibonacci hashing    
		return static_cast<size_t>(x ^ (x >> 16));
	}
	
	public:
		explicit FlatSet32(size_t expected) {
			size_t cap = 16;
			while (cap < expected * 2) cap <<= 1; // load factor <= 0.5
			slots_.assign(cap, EMPTY);
			taken_.assign(cap, 0);
			mask_ = cap - 1;
		}
		void insert(int32_t v) {    
			if (v == EMPTY) { 
				has_sentinel_ = true; 
				return; 
			}    
			size_t i = hash(v) & mask_;    
			while (slots_[i] != EMPTY) {        
				if (slots_[i] == v) return;          // dedupe on insert        
				i = (i + 1) & mask_;    
			}    
			slots_[i] = v;
		}// Returns true exactly once per distinct value present in the set.
		
		bool match_once(int32_t v) {    
			if (v == EMPTY) {        
				if (has_sentinel_ && !sentinel_taken_) { 
				sentinel_taken_ = true; 
				return true; 
				}        
				return false;    
			}    
			size_t i = hash(v) & mask_;    
			while (slots_[i] != EMPTY) {        
				if (slots_[i] == v) {            
					if (!taken_[i]) { 
					taken_[i] = 1; 
					return true; 
					}            
					return false;        
				}        
				i = (i + 1) & mask_;    
			}    
			return false;
		}
	};
	
	// ---------------------------------------------------------------------------
	// Radix partitioning: split by the top RADIX_BITS of the value so that each
	// partition-pair fits in L2 cache during the hash phase (Mechanical Sympathy).
	// A value belongs to exactly one partition, so global uniqueness is preserved.
	// ---------------------------------------------------------------------------
	constexpr int RADIX_BITS = 8;                    // 256 partitions
	constexpr size_t NUM_PARTS = size_t{1} << RADIX_BITS;
	static inline size_t part_of(int32_t v) {
		return static_cast<uint32_t>(v) >> (32 - RADIX_BITS);
	}
	static std::vector<std::vector<int32_t>>
	
	radix_partition(const std::vector<int32_t>& in) {
		std::vector<size_t> counts(NUM_PARTS, 0);
		for (int32_t v : in) ++counts[part_of(v)];   // pass 1: count
		std::vector<std::vector<int32_t>> parts(NUM_PARTS);
		for (size_t p = 0; p < NUM_PARTS; ++p) parts[p].reserve(counts[p]);
		for (int32_t v : in) parts[part_of(v)].push_back(v); // pass 2: scatter
		return parts;
	}
	
	// ---------------------------------------------------------------------------
	// Fast path: multi-threaded partitioned hash set intersection.
	// ---------------------------------------------------------------------------
	std::vector<int32_t> intersect_fast(const std::vector<int32_t>& a, const std::vector<int32_t>& b, unsigned num_threads = 0) {
		if (num_threads == 0)
			num_threads = std::max(1u, std::thread::hardware_concurrency());
			auto pa = radix_partition(a);
			auto pb = radix_partition(b);
			std::atomic<size_t> next_part{0};
			std::vector<std::vector<int32_t>> locals(num_threads);
			std::vector<std::thread> pool;
			pool.reserve(num_threads);
			for (unsigned t = 0; t < num_threads; ++t) {    
				pool.emplace_back([&, t] {        
					auto& out = locals[t];        
					for (;;) {            
						size_t p = next_part.fetch_add(1, std::memory_order_relaxed);            
						if (p >= NUM_PARTS) break;            
						const auto& build_side = (pa[p].size() <= pb[p].size()) ? pa[p] : pb[p];            
						const auto& probe_side = (pa[p].size() <= pb[p].size()) ? pb[p] : pa[p];            
						if (build_side.empty() || probe_side.empty()) continue;            
						FlatSet32 set(build_side.size());            
						for (int32_t v : build_side) set.insert(v);            
						for (int32_t v : probe_side) if (set.match_once(v)) out.push_back(v);        
					}    
				});
			}
			for (auto& th : pool) th.join();
			std::vector<int32_t> result;
			size_t total = 0;
			for (auto& l : locals) total += l.size();
			result.reserve(total);
			for (auto& l : locals) result.insert(result.end(), l.begin(), l.end());
			return result;
	}
	
	// ---------------------------------------------------------------------------
	// Verification Oracle (L14): trusted scalar reference implementation.
	// ---------------------------------------------------------------------------
	std::vector<int32_t> intersect_oracle(std::vector<int32_t> a,
	std::vector<int32_t> b) {
		std::sort(a.begin(), a.end());
		a.erase(std::unique(a.begin(), a.end()), a.end());
		std::sort(b.begin(), b.end());
		b.erase(std::unique(b.begin(), b.end()), b.end());
		std::vector<int32_t> out;
		std::set_intersection(a.begin(), a.end(), b.begin(), b.end(),
		std::back_inserter(out));
		return out;
	}
		
	// ---------------------------------------------------------------------------
	// Golden Tests: functional equivalence, fast vs oracle (order-insensitive).
	// ---------------------------------------------------------------------------
	static bool equivalent(std::vector<int32_t> fast, std::vector<int32_t> ref) {
		std::sort(fast.begin(), fast.end());
		return fast == ref;
	}
	bool run_golden_tests() {
		constexpr int32_t MIN = std::numeric_limits<int32_t>::min();
		constexpr int32_t MAX = std::numeric_limits<int32_t>::max();
		struct Case { const char* name; std::vector<int32_t> a, b; };
		std::vector<Case> cases = {
			{"GT-01 empty vs empty",      {},                    {}},
			{"GT-02 empty vs data",       {},                    {1, 2, 3}},
			{"GT-03 disjoint",            {1, 2, 3},             {4, 5, 6}},
			{"GT-04 all duplicates",      {7, 7, 7, 7},          {7, 7}},
			{"GT-05 boundary MIN/MAX",    {MIN, MAX, 0, MIN},    {MAX, MIN, -1}},
			{"GT-06 negatives",           {-5, -4, -3, -4},      {-4, -5, 9}},
			{"GT-07 identical arrays",    {1, 2, 3, 2, 1},       {1, 2, 3, 2, 1}},
		};
		// GT-08 randomized corpus (seed_policy: strict -> fixed seed = reproducible)
		std::mt19937 rng(0xA1EE5u);
		std::uniform_int_distribution<int32_t> dist(-100000, 100000);
		Case rnd{"GT-08 randomized (seeded)", {}, {}};
		for (int i = 0; i < 200000; ++i) rnd.a.push_back(dist(rng));
		for (int i = 0; i < 150000; ++i) rnd.b.push_back(dist(rng));
		cases.push_back(std::move(rnd));
		bool all_pass = true;
		for (auto& c : cases) {    
			bool ok = equivalent(intersect_fast(c.a, c.b), intersect_oracle(c.a, c.b));    
			std::printf("[GOLDEN] %-28s  %s\n", c.name, ok ? "PASS" : "FAIL");    
			all_pass = all_pass && ok;
		}
		return all_pass;
	}
		
	// ---------------------------------------------------------------------------
	// Benchmark (RFC-0009): 3 warmup runs (discarded), 10 measured (averaged),
	// >=2s cooldown between measured runs. Metric: throughput (elements/second).
	// ---------------------------------------------------------------------------
	void run_benchmark(size_t n) {
		std::printf("[BENCH ] Generating 2 x %zu int32 elements...\n", n);
		std::mt19937 rng(0xBEEFu); // fixed seed: reproducibility_policy
		std::uniform_int_distribution<int32_t> dist(
		std::numeric_limits<int32_t>::min(), std::numeric_limits<int32_t>::max());
		std::vector<int32_t> a(n), b(n);
		for (auto& v : a) v = dist(rng);
		for (auto& v : b) v = dist(rng);
		using clock = std::chrono::steady_clock;for (int w = 0; w < 3; ++w) {                     
			// warmup, discarded    
			volatile size_t sink = intersect_fast(a, b).size();    
			(void)sink;    
			std::printf("[BENCH ] Warmup %d/3 done (discarded)\n", w + 1);
		}
		double total_sec = 0.0;
		size_t matches = 0;
		for (int r = 0; r < 10; ++r) {                    
		// measured    auto 
			t0 = clock::now();    
			auto out = intersect_fast(a, b);    
			auto t1 = clock::now();    
			double sec = std::chrono::duration<double>(t1 - t0).count();    
			total_sec += sec;    
			matches = out.size();    
			std::printf("[BENCH ] Run %2d/10: %.4f s\n", r + 1, sec);    
			std::this_thread::sleep_for(std::chrono::seconds(2)); 
			// cooldown
		}
		double avg = total_sec / 10.0;
		std::printf("[BENCH ] Matches: %zu | Avg: %.4f s | Throughput: %.2f M elem/s\n", matches, avg, (2.0 * static_cast<double>(n)) / avg / 1e6);
	}
} 
//namespace aiees

// ---------------------------------------------------------------------------
// Entry point. Usage: ./intersect [array_size]   (default 16,777,216 per array)
// Golden Tests gate the benchmark: FAIL => non-conformant => exit(1).
// ---------------------------------------------------------------------------
int main(int argc, char** argv) {
	std::printf("AI-EES Artifact AIEES-ART-20250614-XEON-INTERSECT-0001\n");
	if (!aiees::run_golden_tests()) {
		std::printf("[RESULT] GOLDEN TESTS FAILED - ARTIFACT NON-CONFORMANT\n");
		return 1;
	}
	std::printf("[RESULT] ALL GOLDEN TESTS PASSED\n");
	size_t n = (argc > 1) ? std::strtoull(argv[1], nullptr, 10) : (size_t{1} << 24);
	aiees::run_benchmark(n);
	return 0;
}