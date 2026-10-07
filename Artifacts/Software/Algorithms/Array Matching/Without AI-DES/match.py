# -*- coding: utf-8 -*-
"""
Created on Tue Jul 14 16:50:56 2026

@author: arvasis
"""

#Fastest Integer Matching Between Two Arrays
#The fastest general approach is using a hash set, giving O(n + m) time complexity instead of the naive O(n × m) nested loop.
#Approach 1: Hash Set — O(n + m) ⚡ (Fastest for general cases)
#Python
def find_matches(arr1, arr2):    
    set1 = set(arr1)                    # O(n) build    
    return [x for x in set2_scan(arr2, set1)]

def set2_scan(arr2, set1):    
    seen = set()    
    for x in arr2:                      # O(m) scan        
        if x in set1 and x not in seen: # O(1) lookup            
            seen.add(x)            
    yield x 
# Usage
a = [4, 9, 5, 1, 8]
b = [9, 4, 9, 8, 4]
print(find_matches(a, b))   # [9, 4, 8]

#Or the one-liner (simplest and very fast — implemented in C internally):
#matches = set(arr1) & set(arr2)
