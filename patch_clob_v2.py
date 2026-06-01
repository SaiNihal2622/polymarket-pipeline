"""Startup patch: Fix order_version_mismatch for Polymarket CLOB V2.
Run this before demo_runner.py to patch the signing libraries.
"""
import importlib
import sys

# Patch 1: Domain version "1" -> "2" in py_order_utils
try:
    import py_order_utils.builders.base_builder as bb
    if hasattr(bb, 'BaseBuilder'):
        orig = bb.BaseBuilder._get_domain_separator
        def patched(self, chain_id, verifying_contract):
            from poly_eip712_structs import make_domain
            return make_domain(
                name="Polymarket CTF Exchange",
                version="2",
                chainId=str(chain_id),
                verifyingContract=verifying_contract,
            )
        bb.BaseBuilder._get_domain_separator = patched
        print("[patch] CLOB domain version: 1 -> 2")
except Exception as e:
    print(f"[patch] WARNING: Could not patch domain version: {e}")

# Patch 2: Add version=2 to order body
try:
    import py_clob_client.utilities as util
    orig_fn = util.order_to_json
    def patched_order_to_json(order, owner, orderType, post_only=False):
        result = orig_fn(order, owner, orderType, post_only)
        if "order" in result and "version" not in result["order"]:
            result["order"]["version"] = 2
        return result
    util.order_to_json = patched_order_to_json
    print("[patch] Order body: added version=2")
except Exception as e:
    print(f"[patch] WARNING: Could not patch order version: {e}")

print("[patch] Polymarket CLOB V2 patches applied successfully")