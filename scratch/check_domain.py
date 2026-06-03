"""Check the actual domain separator being used."""
import sys, os, shutil
for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")

from py_order_utils.builders.base_builder import BaseBuilder
from py_order_utils.signer import Signer as US
from eth_account import Account as EA

key = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"
acct = EA.from_key(key)
signer = US(acct._key_obj)

bb = BaseBuilder("0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", 137, signer, lambda: 123)
ds = bb.domain_separator

print("Domain separator type:", type(ds), flush=True)
print("Has signable_bytes:", hasattr(ds, "signable_bytes"), flush=True)

# Check if version attribute exists
try:
    print("Version value:", ds.version, flush=True)
except:
    print("No version attribute", flush=True)

# Check all attributes
for attr in dir(ds):
    if not attr.startswith("_"):
        try:
            val = getattr(ds, attr)
            if not callable(val):
                print(f"  {attr} = {val}", flush=True)
        except:
            pass

# Compute the domain hash
from eth_utils import keccak
ds_bytes = ds.signable_bytes()
print(f"\nDomain signable_bytes (first 64 hex): {ds_bytes.hex()[:64]}", flush=True)
print(f"Domain hash: {keccak(ds_bytes).hex()}", flush=True)

# Compare with expected domain hash for version=2
# The EIP-712 type hash for (name, version, chainId, verifyingContract) is:
# keccak("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
import hashlib
expected_type_hash = keccak(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
print(f"\nExpected type hash: {expected_type_hash.hex()}", flush=True)
