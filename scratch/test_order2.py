"""Test CLOB order through Vercel proxy - check contract config."""
import sys
for mod_name in list(sys.modules.keys()):
    if 'py_order_utils' in mod_name or 'py_clob_client' in mod_name:
        del sys.modules[mod_name]

from py_clob_client.config import get_contract_config

config = get_contract_config(137, False)
print(f'Exchange: {config.exchange}')
print(f'Neg risk exchange: {config.neg_risk_exchange}')
print(f'All attrs: {[x for x in dir(config) if not x.startswith("__")]}')