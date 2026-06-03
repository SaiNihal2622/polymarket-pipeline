"""Startup patch: LEGACY SHIM — no longer needed with py_clob_client_v2.

The V2 SDK (py_clob_client_v2) handles domain version "2" natively.
This file is kept as a no-op import so existing startup code doesn't break.
"""
import importlib
import sys

# Check if we're using the V2 SDK (preferred) or the old V1 SDK
_USING_V2 = False
try:
    from py_clob_client_v2.client import ClobClient as V2Client
    _USING_V2 = True
    print("[patch] Using py_clob_client_v2 — no patches needed (V2 native)")
except ImportError:
    print("[patch] py_clob_client_v2 not found — falling back to V1 patches")

# Only apply legacy patches if V2 SDK is NOT available
if not _USING_V2:
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
        import inspect
        _sig = inspect.signature(orig_fn)
        _param_count = len(_sig.parameters)
        
        if _param_count >= 4:
            def patched_order_to_json(order, owner, orderType, post_only=False):
                result = orig_fn(order, owner, orderType, post_only)
                if "order" in result and "version" not in result["order"]:
                    result["order"]["version"] = 2
                return result
        else:
            def patched_order_to_json(order, owner, orderType):
                result = orig_fn(order, owner, orderType)
                if "order" in result and "version" not in result["order"]:
                    result["order"]["version"] = 2
                return result
        
        util.order_to_json = patched_order_to_json
        try:
            import py_clob_client.client as _client_mod
            _client_mod.order_to_json = patched_order_to_json
        except Exception:
            pass
        print(f"[patch] Order body: added version=2 (detected {_param_count} params)")
    except Exception as e:
        print(f"[patch] WARNING: Could not patch order version: {e}")

    # Patch 3: Patch post_order directly to add version=2 to the body
    try:
        import py_clob_client.client as _client_mod
        _orig_post_order = _client_mod.ClobClient.post_order
        
        def patched_post_order(self, order, orderType=None):
            from py_clob_client.clob_types import OrderType
            if orderType is None:
                orderType = OrderType.GTC
            from py_clob_client.headers.headers import create_level_2_headers, RequestArgs
            from py_clob_client.endpoints import POST_ORDER
            from py_clob_client.http_helpers.helpers import post as _post
            from py_clob_client.clob_types import ApiCreds
            
            self.assert_level_2_auth()
            body = _client_mod.order_to_json(order, self.creds.api_key, orderType)
            
            body["version"] = 2
            if "order" in body and isinstance(body["order"], dict):
                body["order"]["version"] = 2
            
            headers = create_level_2_headers(
                self.signer,
                self.creds,
                RequestArgs(method="POST", request_path=POST_ORDER, body=body),
            )
            return _post("{}{}".format(self.host, POST_ORDER), headers=headers, data=body)
        
        _client_mod.ClobClient.post_order = patched_post_order
        print("[patch] post_order: patched to inject version=2 into body")
    except Exception as e:
        print(f"[patch] WARNING: Could not patch post_order: {e}")

print("[patch] CLOB V2 patch module loaded")