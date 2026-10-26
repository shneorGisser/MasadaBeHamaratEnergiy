"""Independent reference models from open-source libraries, used only to cross-check ours.

Nothing in the app imports this package at runtime. The libraries are optional dev
dependencies (`pip install -e .[reference]`). The tests skip, and report the skip, when a
library is missing, exactly like the ngspice cross-validation.
"""
