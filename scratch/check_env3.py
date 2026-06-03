import os
for k in ['POLY_PRIVATE_KEY', 'POLY_API_KEY', 'POLY_API_SECRET', 'POLY_API_PASSPHRASE']:
    v = os.environ.get(k, '')
    if v:
        print(f'{k}: len={len(v)}, starts_with={repr(v[:10])}...')
    else:
        print(f'{k}: EMPTY or MISSING')