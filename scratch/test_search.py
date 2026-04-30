import sys
import os
sys.path.append(r"C:\Users\saini\Desktop\iplclaude\polymarket-pipeline")

import resolver
import logging

logging.basicConfig(level=logging.INFO)

def test_search():
    q = "Will the price of Bitcoin be above $56,000 on April 6?"
    print(f"Testing search for: {q}")
    res = resolver._resolve_via_search(q)
    print(f"Result: {res}")

if __name__ == "__main__":
    test_search()
