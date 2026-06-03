"""Register Cloudflare workers.dev subdomain and deploy worker via API."""
import httpx, json, os

# Read the wrangler OAuth token
cfg_path = os.path.join(os.path.expanduser("~"), ".wrangler", "config", "default.toml")
with open(cfg_path, "r") as f:
    content = f.read()
    print(f"Config content (first 200): {content[:200]}")