import sys
for m in list(sys.modules.keys()):
    if 'py_order_utils' in m or 'py_clob_client' in m:
        del sys.modules[m]
from py_order_utils.builders.base_builder import BaseBuilder
import inspect
src = inspect.getsource(BaseBuilder._get_domain_separator)
print(src)