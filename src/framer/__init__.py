"""
Framer - Generate 3D-printable frames for PCBs from KiCAD files or JSON specifications.
"""

from .framer import Framer, Hole, generate_scad, get_pcb_info

__all__ = ["Framer", "Hole", "generate_scad", "get_pcb_info"]
