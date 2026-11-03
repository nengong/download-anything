"""
Driver Registry and Dynamic Discovery
"""
from typing import List
from drivers.base import BaseDriver
from drivers.pan.lanzou import LanzouDriver
from drivers.pan.quark import QuarkDriver
from drivers.books.shadow_library import ShadowLibraryDriver

def get_default_drivers() -> List[BaseDriver]:
    """Return an instantiated list of all active drivers."""
    return [
        LanzouDriver(),
        QuarkDriver(),
        ShadowLibraryDriver(),
    ]
