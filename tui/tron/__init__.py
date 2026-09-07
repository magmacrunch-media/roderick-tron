"""Roderick Tron — the terminal version.

The rules layer (:mod:`tron.config`, :mod:`tron.tilemap`, :mod:`tron.player`,
:mod:`tron.entities`, :mod:`tron.cells`) imports nothing outside the standard
library, so ``tests/test_physics.py`` runs with nothing but pytest on the
machine. The engine appears only in the screens.
"""

__version__ = "0.1.0"
