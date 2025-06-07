#!/usr/bin/env python3

from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
import sexpdata

@dataclass
class Hole:
    """Represents a hole in the PCB"""
    x: float  # X coordinate from left edge
    y: float  # Y coordinate from top edge
    diameter: float  # Diameter of the hole
    reference: str  # Reference designator or description

class Framer:
    def __init__(self, pcb_file: str, verbose: bool = False):
        """Initialize Framer with path to KiCAD PCB file"""
        self.pcb_file = pcb_file
        self.verbose = verbose
        self.min_x: Optional[float] = None
        self.max_x: Optional[float] = None
        self.min_y: Optional[float] = None
        self.max_y: Optional[float] = None
        self.holes: List[Hole] = []
        self._parse_pcb_file()

    def _debug(self, msg: str, level: int = 0):
        """Print debug message if verbose mode is enabled"""
        if self.verbose:
            indent = "  " * level
            print(f"DEBUG: {indent}{msg}")

    def _format_element(self, element: Any) -> str:
        """Format an S-expression element for debugging"""
        if isinstance(element, list):
            return f"[{', '.join(self._format_element(e) for e in element)}]"
        elif isinstance(element, sexpdata.Symbol):
            return f"Symbol({element})"
        else:
            return str(element)

    def _update_bounds(self, x: float, y: float):
        """Update the PCB boundary coordinates"""
        old_min_x = self.min_x
        old_max_x = self.max_x
        old_min_y = self.min_y
        old_max_y = self.max_y

        if self.min_x is None or x < self.min_x:
            self.min_x = x
        if self.max_x is None or x > self.max_x:
            self.max_x = x
        if self.min_y is None or y < self.min_y:
            self.min_y = y
        if self.max_y is None or y > self.max_y:
            self.max_y = y

        if self.verbose and (old_min_x != self.min_x or old_max_x != self.max_x or 
                           old_min_y != self.min_y or old_max_y != self.max_y):
            self._debug(f"Updated bounds: ({self.min_x:.2f}, {self.min_y:.2f}) to ({self.max_x:.2f}, {self.max_y:.2f})")

    def _get_xy_from_at(self, element: List[Any]) -> Tuple[float, float]:
        """Extract x,y coordinates from an 'at' element"""
        for item in element:
            if isinstance(item, list) and len(item) >= 3 and item[0] == sexpdata.Symbol('at'):
                return float(item[1]), float(item[2])
        return None, None

    def _get_drill_size(self, element: List[Any]) -> Optional[float]:
        """Extract drill size from a MountingHole footprint name
        Example: "MountingHole:MountingHole_2.2mm_M2" -> 2.2
        """
        if not isinstance(element[1], str):
            return None
            
        footprint_name = element[1]
        self._debug(f"Extracting size from footprint: {footprint_name}", 2)
        
        # Look for the pattern _DDmm or _DD.DDmm where D is a digit
        parts = footprint_name.split('_')
        for part in parts:
            if part.endswith('mm'):
                try:
                    # Remove the 'mm' and convert to float
                    size = float(part[:-2])
                    self._debug(f"Found hole size: {size}mm", 2)
                    return size
                except ValueError:
                    continue
        
        self._debug("Could not find hole size in footprint name", 2)
        return None

    def _get_reference(self, element: List[Any]) -> str:
        """Extract reference from a footprint by finding (property "Reference" "REF**") structure"""
        for item in element:
            if not isinstance(item, list):
                continue
            
            if len(item) >= 3 and isinstance(item[0], sexpdata.Symbol):
                if str(item[0]) == 'property' and str(item[1]) == 'Reference':
                    self._debug(f"Found reference: {item[2]}", 2)
                    return str(item[2])
        
        self._debug("Could not find reference property", 2)
        return "Unknown"

    def _process_edge_cut(self, element: List[Any]):
        """Process an edge cut element (gr_line, gr_arc, gr_circle, etc)"""
        element_type = str(element[0])
        self._debug(f"Processing Edge.Cuts element: {element_type}", 1)
        self._debug(f"Raw element data: {self._format_element(element)}", 2)

        # Extract coordinates based on element type
        if element_type == 'gr_rect':
            # Handle rectangles - just need start and end points
            start_x = start_y = end_x = end_y = None
            for item in element:
                if not isinstance(item, list):
                    continue
                    
                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""
                
                if item_type == 'start':
                    start_x, start_y = float(item[1]), float(item[2])
                    self._debug(f"Found rectangle start point: ({start_x:.2f}, {start_y:.2f})", 2)
                elif item_type == 'end':
                    end_x, end_y = float(item[1]), float(item[2])
                    self._debug(f"Found rectangle end point: ({end_x:.2f}, {end_y:.2f})", 2)
            
            if start_x is not None and start_y is not None:
                self._update_bounds(start_x, start_y)
            if end_x is not None and end_y is not None:
                self._update_bounds(end_x, end_y)

        elif element_type in ['gr_line', 'segment']:
            # Look for start and end coordinates
            for item in element:
                if not isinstance(item, list):
                    continue
                    
                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""
                
                if item_type == 'start':
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found start point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == 'end':
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found end point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == 'pts':  # For newer KiCAD versions
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == 'xy':
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)
                elif item_type == 'xy':  # Direct xy coordinate
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found xy point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)

        elif element_type in ['gr_arc', 'gr_circle']:
            center_x = center_y = None
            radius = None
            start_x = start_y = None
            end_x = end_y = None
            
            for item in element:
                if not isinstance(item, list):
                    continue
                    
                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""
                
                if item_type == 'center':
                    center_x, center_y = float(item[1]), float(item[2])
                elif item_type == 'start':
                    start_x, start_y = float(item[1]), float(item[2])
                elif item_type == 'end':
                    end_x, end_y = float(item[1]), float(item[2])
                elif item_type == 'radius':
                    radius = float(item[1])
                elif item_type == 'pts':  # For newer KiCAD versions
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == 'xy':
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)

            # Update bounds with all found points
            if center_x is not None and center_y is not None:
                self._update_bounds(center_x, center_y)
                if radius is not None:
                    # For circles, add points at extremes
                    self._update_bounds(center_x - radius, center_y)
                    self._update_bounds(center_x + radius, center_y)
                    self._update_bounds(center_x, center_y - radius)
                    self._update_bounds(center_x, center_y + radius)
            
            if start_x is not None and start_y is not None:
                self._update_bounds(start_x, start_y)
            if end_x is not None and end_y is not None:
                self._update_bounds(end_x, end_y)

        elif element_type == 'gr_curve':
            # Handle Bezier curves - use control points to approximate bounds
            for item in element:
                if not isinstance(item, list):
                    continue
                    
                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""
                
                if item_type in ['start', 'end', 'ctrl1', 'ctrl2']:
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found {item_type} point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == 'pts':  # For newer KiCAD versions
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == 'xy':
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)

    def _process_footprint(self, element: List[Any]):
        """Process a footprint element, looking specifically for mounting holes"""

        self._debug(f"Processing footprint: {element}", 1)
        # First check if this is a mounting hole footprint
        footprint_name = None
#        if element[0] != sexpdata.Symbol or not element[1].startswith("MountingHole"):
        if element[0] != sexpdata.Symbol("footprint") or not element[1].startswith("MountingHole"):               
            self._debug(f"Skipping non-mounting hole footprint: {element[0]}, {element[1]}", 1)
            return

        x, y = self._get_xy_from_at(element)
        if x is None or y is None:
            return
        self._debug(f"Found mounting hole at ({x:.2f}, {y:.2f})", 1)
        drill_size = self._get_drill_size(element)

        if drill_size is not None:
            reference = self._get_reference(element)
            if self.verbose:
                self._debug(f"Found mounting hole {reference} at ({x:.2f}, {y:.2f}) with diameter {drill_size:.2f}mm", 1)
            self.holes.append(Hole(x=x, y=y, diameter=drill_size, reference=reference))

    def _parse_pcb_file(self):
        """Parse the KiCAD PCB file to extract dimensions and holes"""
        self._debug(f"Opening PCB file: {self.pcb_file}")
        with open(self.pcb_file, 'r') as f:
            content = f.read()

        # Parse the S-expression
        self._debug("Parsing PCB file as S-expression")
        pcb = sexpdata.loads(content)
        self._debug(f"PCB file root element type: {type(pcb)}")
        self._debug(f"Number of top-level elements: {len(pcb)}")

        edge_cut_count = 0
        mounting_hole_count = 0

        # Process all elements in the PCB file
        for element in pcb:
            if not isinstance(element, list) or not element:
                continue

            element_type = element[0]
            if not isinstance(element_type, sexpdata.Symbol):
                continue

            # First check if this element is on the Edge.Cuts layer
            is_edge_cut = False
            for item in element:
                if isinstance(item, list) and len(item) >= 2:
                    if isinstance(item[0], sexpdata.Symbol) and str(item[0]) == 'layer':
                        if str(item[1]) == 'Edge.Cuts':
                            is_edge_cut = True
                            break

            element_type = str(element_type)
            if is_edge_cut:
                edge_cut_count += 1
                self._debug(f"Found Edge.Cuts element: {element_type}", 1)
                self._process_edge_cut(element)
            elif element_type in ('module', 'footprint'):
                old_hole_count = len(self.holes)
                self._process_footprint(element)
                if len(self.holes) > old_hole_count:
                    mounting_hole_count += 1

        self._debug(f"Processed {edge_cut_count} edge cut elements")
        self._debug(f"Found {mounting_hole_count} mounting holes")
        
        if edge_cut_count == 0:
            self._debug("WARNING: No edge cut elements found! Board outline may be incomplete or missing.")
            self._debug("First few elements of PCB file for debugging:")
            for i, element in enumerate(pcb[:5]):
                self._debug(f"Element {i}: {self._format_element(element)}", 1)

    def get_dimensions(self) -> Tuple[float, float]:
        """Return the PCB dimensions as (width, height)"""
        if any(v is None for v in [self.min_x, self.max_x, self.min_y, self.max_y]):
            raise ValueError("PCB dimensions could not be determined from edge cuts")
        width = self.max_x - self.min_x
        height = self.max_y - self.min_y
        if self.verbose:
            self._debug(f"Final PCB dimensions: {width:.2f}mm x {height:.2f}mm")
        return (width, height)

    def get_holes(self) -> List[Hole]:
        """Return list of all holes found in the PCB"""
        # Adjust hole coordinates to be relative to board edges
        if self.min_x is not None and self.min_y is not None:
            for hole in self.holes:
                hole.x -= self.min_x
                hole.y -= self.min_y
                if self.verbose:
                    self._debug(f"Adjusted hole {hole.reference} to relative coordinates: ({hole.x:.2f}, {hole.y:.2f})")
        return self.holes

if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) != 2:
        print("Usage: framer.py <kicad_pcb_file>")
        sys.exit(1)
        
    framer = Framer(sys.argv[1])  # verbose=True by default
    width, height = framer.get_dimensions()
    print(f"\nPCB Dimensions: {width:.2f}mm x {height:.2f}mm")
    print("\nHoles found:")
    for hole in framer.get_holes():
        print(f"- {hole.reference}: ({hole.x:.2f}mm, {hole.y:.2f}mm) diameter: {hole.diameter}mm") 