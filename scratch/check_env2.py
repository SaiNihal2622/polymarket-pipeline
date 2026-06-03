import os
from dotenv import load_dotenv
load_dotenv(override=True)
print("POLY_API_KEY:", repr(os.getenv("POLY_API_KEY", "")[:20]) if os.getenv("POLY_API_KEY") else "MISSING")
print("POLY_SECRET:", repr(os.getenv("POLY_SECRET", "")[:20]) if os.getenv("POLY_SECRET") else "MISSING")
print("POLY_PRIVATE_KEY:", repr(os.getenv("POLY_PRIVATE_KEY", "")[:20]) if os.getenv("POLY_PRIVATE_KEY") else "MISSING")
print("POLY_API_SECRET:", repr(os.getenv("POLY_API_SECRET", "")[:20]) if os.getenv("POLY_API_SECRET") else "MISSING")
print("POLY_API_PASSPHRASE:", repr(os.getenv("POLY_API_PASSPHRASE", "")[:20]) if os.getenv("POLY_API_PASSPHRASE") else "MISSING")

# Also check all POLY vars
for k, v in os.environ.items():
    if 'POLY' in k.upper():
        print(f"  ENV {k} = {v[:30]}...")