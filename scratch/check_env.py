import os
# Check what tokens are available
env_vars = ['GITHUB_TOKEN', 'GH_TOKEN', 'GIST_ID', 'POLYMARKET_HOST', 'RENDER_EXTERNAL_URL', 'RAILWAY_STATIC_URL']
for k in env_vars:
    v = os.getenv(k, '')
    if v:
        print(f"{k} = {v[:20]}...")
    else:
        print(f"{k} = (not set)")

# Check for .env file
import pathlib
env_file = pathlib.Path('.env')
if env_file.exists():
    lines = env_file.read_text(encoding='utf-8').splitlines()
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key = line.split('=', 1)[0].strip()
            print(f"  .env has: {key}")