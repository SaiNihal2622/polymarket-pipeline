"""Check py-clob-client config for exchange addresses and order version."""
import sys
for m in list(sys.modules.keys()):
    if 'py_order_utils' in m or 'py_clob_client' in m:
        del sys.modules[m]

from py_clob_client.config import get_contract_config

# Check both regular and neg_risk configs
for neg in [False, True]:
    cfg = get_contract_config(137, neg)
    print(f"\nneg_risk={neg}:")
    print(f"  exchange: {cfg.exchange}")
    attrs = [x for x in dir(cfg) if not x.startswith('_') and x != 'exchange']
    for a in attrs:
        print(f"  {a}: {getattr(cfg, a)}")