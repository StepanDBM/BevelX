import sys

BEVELX_PATH = r"\...\BevelX_SDBM"
if BEVELX_PATH not in sys.path:
    sys.path.insert(0, BEVELX_PATH)

import BX_bootstrap as BX_bootstrap
BX_bootstrap.launch(reload=True)