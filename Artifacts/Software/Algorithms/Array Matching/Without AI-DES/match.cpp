
//C++
#include <iostream>
#include <vector>
#include <unordered_set>std::vector<int> 

findMatches(const std::vector<int>& a, const std::vector<int>& b) {    
	std::unordered_set<int> lookup(a.begin(), a.end()); // O(n)    
	std::unordered_set<int> added;    std::vector<int> result;    
	result.reserve(std::min(a.size(), b.size()));    
	for (int x : b) {                                   // O(m)        
		if (lookup.count(x) && added.insert(x).second)            
			result.push_back(x);    
	}    
	return result;
}

int main() {    
	std::vector<int> a = {4, 9, 5, 1, 8};    
	std::vector<int> b = {9, 4, 9, 8, 4};    
	for (int x : findMatches(a, b))        
		std::cout << x << " ";          // 9 4 8
}

//Approach 2: Sort + Two Pointers — O(n log n + m log m)
//Better cache locality, no hashing overhead. Often faster in practice for medium-sized arrays or when memory is tight.

#include <algorithm>
#include <vector>std::vector<int> 

findMatchesSorted(std::vector<int> a, std::vector<int> b) {    
	std::sort(a.begin(), a.end());    
	std::sort(b.begin(), b.end());    
	std::vector<int> result;    
	size_t i = 0, j = 0;    
	while (i < a.size() && j < b.size()) {        
		if (a[i] < b[j])      ++i;        
		else if (a[i] > b[j]) ++j;        
		else {            
			if (result.empty() || result.back() != a[i])                
				result.push_back(a[i]);   // skip duplicates            
			++i; 
			++j;        
		}    
	}    
	return result;
}

//Approach 3: Bitmap / Boolean Array — O(n + m), fastest if range is small
//If integers fall in a known small range (e.g., 0 to 1,000,000), this beats everything:

std::vector<int> findMatchesBitmap(const std::vector<int>& a, const std::vector<int>& b, int maxVal) {    
	std::vector<bool> present(maxVal + 1, false);    
	for (int x : a) present[x] = true;    
	std::vector<bool> reported(maxVal + 1, false);    
	std::vector<int> result;    
	for (int x : b) {        
		if (present[x] && !reported[x]) {            
		reported[x] = true;            
		result.push_back(x);        
		}    
	}    
	return result;
}
//Performance Summary
//MethodTimeSpaceBest when...Nested loopsO(n·m)O(1)Never (tiny arrays only)Hash setO(n+m)O(n)General purposeSort + two pointersO(n log n)O(1)*Arrays already sorted / memory-constrainedBitmapO(n+m)O(range)Small known value range
//* If sorting in place.
//Rule of thumb: Use the hash set. Switch to bitmap if the integer range is small, or two-pointers if the arrays are already sorted (then it's O(n + m) with zero extra memory).