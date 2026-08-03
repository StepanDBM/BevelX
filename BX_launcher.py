# BX_launcher.py
# Shelf-friendly launcher for BevelX.

from __future__ import print_function


def launch():
    import BX_bootstrap
    return BX_bootstrap.launch(reload=True)


if __name__ == "__main__":
    launch()
