#!/usr/bin/env python3
"""
Framer - Generate 3D-printable frames for PCBs from KiCAD files or JSON specifications.
"""

import json
import os
import re
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import sexpdata


@dataclass
class Hole:
    """Represents a hole in the PCB"""

    x: float  # X coordinate from left edge
    y: float  # Y coordinate from top edge
    diameter: float  # Diameter of the hole
    reference: str  # Reference designator or description


class Framer:
    """Parse KiCAD PCB files to extract dimensions and mounting holes."""

    def __init__(self, pcb_file: Optional[str] = None, verbose: bool = False):
        """Initialize Framer with optional path to KiCAD PCB file.

        Args:
            pcb_file: Path to KiCAD PCB file (optional, can load later via load_from_* methods)
            verbose: Enable debug output
        """
        self.pcb_file = pcb_file
        self.verbose = verbose
        self.min_x: Optional[float] = None
        self.max_x: Optional[float] = None
        self.min_y: Optional[float] = None
        self.max_y: Optional[float] = None
        self.holes: List[Hole] = []
        self._holes_adjusted = False

        # Properties for JSON-loaded boards
        self.board_width: Optional[float] = None
        self.board_height: Optional[float] = None
        self.margin: float = 2.0  # Default margin

        if pcb_file:
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

        if self.verbose and (
            old_min_x != self.min_x
            or old_max_x != self.max_x
            or old_min_y != self.min_y
            or old_max_y != self.max_y
        ):
            self._debug(
                f"Updated bounds: ({self.min_x:.2f}, {self.min_y:.2f}) to ({self.max_x:.2f}, {self.max_y:.2f})"
            )

    def _get_xy_from_at(
        self, element: List[Any]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Extract x,y coordinates from an 'at' element"""
        for item in element:
            if (
                isinstance(item, list)
                and len(item) >= 3
                and item[0] == sexpdata.Symbol("at")
            ):
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
        parts = footprint_name.split("_")
        for part in parts:
            if part.endswith("mm"):
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
                if str(item[0]) == "property" and str(item[1]) == "Reference":
                    self._debug(f"Found reference: {item[2]}", 2)
                    return str(item[2])

        self._debug("Could not find reference property", 2)
        return "Unknown"

    def _process_edge_cut(self, element: List[Any]):
        """Process an edge cut element (gr_line, gr_arc, gr_circle, etc)"""
        element_type = str(element[0])
        self._debug(f"Processing Edge.Cuts element: {element_type}", 1)
        self._debug(f"Raw element data: {self._format_element(element)}", 2)

        if element_type == "gr_rect":
            start_x = start_y = end_x = end_y = None
            for item in element:
                if not isinstance(item, list):
                    continue

                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""

                if item_type == "start":
                    start_x, start_y = float(item[1]), float(item[2])
                    self._debug(
                        f"Found rectangle start point: ({start_x:.2f}, {start_y:.2f})",
                        2,
                    )
                elif item_type == "end":
                    end_x, end_y = float(item[1]), float(item[2])
                    self._debug(
                        f"Found rectangle end point: ({end_x:.2f}, {end_y:.2f})", 2
                    )

            if start_x is not None and start_y is not None:
                self._update_bounds(start_x, start_y)
            if end_x is not None and end_y is not None:
                self._update_bounds(end_x, end_y)

        elif element_type in ["gr_line", "segment"]:
            for item in element:
                if not isinstance(item, list):
                    continue

                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""

                if item_type == "start":
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found start point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == "end":
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found end point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == "pts":
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == "xy":
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)
                elif item_type == "xy":
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found xy point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)

        elif element_type in ["gr_arc", "gr_circle"]:
            center_x = center_y = None
            radius = None
            start_x = start_y = None
            end_x = end_y = None

            for item in element:
                if not isinstance(item, list):
                    continue

                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""

                if item_type == "center":
                    center_x, center_y = float(item[1]), float(item[2])
                elif item_type == "start":
                    start_x, start_y = float(item[1]), float(item[2])
                elif item_type == "end":
                    end_x, end_y = float(item[1]), float(item[2])
                elif item_type == "radius":
                    radius = float(item[1])
                elif item_type == "pts":
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == "xy":
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)

            if center_x is not None and center_y is not None:
                self._update_bounds(center_x, center_y)
                if radius is not None:
                    self._update_bounds(center_x - radius, center_y)
                    self._update_bounds(center_x + radius, center_y)
                    self._update_bounds(center_x, center_y - radius)
                    self._update_bounds(center_x, center_y + radius)

            if start_x is not None and start_y is not None:
                self._update_bounds(start_x, start_y)
            if end_x is not None and end_y is not None:
                self._update_bounds(end_x, end_y)

        elif element_type == "gr_curve":
            for item in element:
                if not isinstance(item, list):
                    continue

                item_type = str(item[0]) if isinstance(item[0], sexpdata.Symbol) else ""

                if item_type in ["start", "end", "ctrl1", "ctrl2"]:
                    x, y = float(item[1]), float(item[2])
                    self._debug(f"Found {item_type} point: ({x:.2f}, {y:.2f})", 2)
                    self._update_bounds(x, y)
                elif item_type == "pts":
                    for pt in item[1:]:
                        if isinstance(pt, list) and len(pt) >= 3 and str(pt[0]) == "xy":
                            x, y = float(pt[1]), float(pt[2])
                            self._debug(f"Found point: ({x:.2f}, {y:.2f})", 2)
                            self._update_bounds(x, y)

    def _process_footprint(self, element: List[Any]):
        """Process a footprint element, looking specifically for mounting holes"""
        self._debug(f"Processing footprint: {element}", 1)

        if element[0] != sexpdata.Symbol("footprint") or not element[1].startswith(
            "MountingHole"
        ):
            self._debug(
                f"Skipping non-mounting hole footprint: {element[0]}, {element[1]}", 1
            )
            return

        x, y = self._get_xy_from_at(element)
        if x is None or y is None:
            return
        self._debug(f"Found mounting hole at ({x:.2f}, {y:.2f})", 1)
        drill_size = self._get_drill_size(element)

        if drill_size is not None:
            reference = self._get_reference(element)
            if self.verbose:
                self._debug(
                    f"Found mounting hole {reference} at ({x:.2f}, {y:.2f}) with diameter {drill_size:.2f}mm",
                    1,
                )
            self.holes.append(Hole(x=x, y=y, diameter=drill_size, reference=reference))

    def _parse_pcb_file(self):
        """Parse the KiCAD PCB file to extract dimensions and holes"""
        self._debug(f"Opening PCB file: {self.pcb_file}")
        with open(self.pcb_file, "r") as f:
            content = f.read()

        self._debug("Parsing PCB file as S-expression")
        pcb = sexpdata.loads(content)
        self._debug(f"PCB file root element type: {type(pcb)}")
        self._debug(f"Number of top-level elements: {len(pcb)}")

        edge_cut_count = 0
        mounting_hole_count = 0

        for element in pcb:
            if not isinstance(element, list) or not element:
                continue

            element_type = element[0]
            if not isinstance(element_type, sexpdata.Symbol):
                continue

            is_edge_cut = False
            for item in element:
                if isinstance(item, list) and len(item) >= 2:
                    if isinstance(item[0], sexpdata.Symbol) and str(item[0]) == "layer":
                        if str(item[1]) == "Edge.Cuts":
                            is_edge_cut = True
                            break

            element_type = str(element_type)
            if is_edge_cut:
                edge_cut_count += 1
                self._debug(f"Found Edge.Cuts element: {element_type}", 1)
                self._process_edge_cut(element)
            elif element_type in ("module", "footprint"):
                old_hole_count = len(self.holes)
                self._process_footprint(element)
                if len(self.holes) > old_hole_count:
                    mounting_hole_count += 1

        self._debug(f"Processed {edge_cut_count} edge cut elements")
        self._debug(f"Found {mounting_hole_count} mounting holes")

        if edge_cut_count == 0:
            self._debug(
                "WARNING: No edge cut elements found! Board outline may be incomplete or missing."
            )
            self._debug("First few elements of PCB file for debugging:")
            for i, element in enumerate(pcb[:5]):
                self._debug(f"Element {i}: {self._format_element(element)}", 1)

    def load_from_json(self, data: dict):
        """Load board specifications from a JSON dict.

        Expected format:
        {
            "width": float,      # PCB width in mm
            "height": float,     # PCB height in mm
            "mounting_holes": [  # List of mounting holes
                {
                    "x": float,       # X coordinate from left edge in mm
                    "y": float,       # Y coordinate from top edge in mm
                    "diameter": float, # Hole diameter in mm
                    "reference": str   # Reference designator (optional)
                },
                ...
            ]
        }
        """
        self.board_width = float(data["width"])
        self.board_height = float(data["height"])

        # Set bounds for dimension calculations
        self.min_x = 0
        self.min_y = 0
        self.max_x = self.board_width
        self.max_y = self.board_height

        self.holes = []
        for hole_data in data.get("mounting_holes", []):
            self.holes.append(
                Hole(
                    x=float(hole_data["x"]),
                    y=float(hole_data["y"]),
                    diameter=float(hole_data["diameter"]),
                    reference=hole_data.get("reference", "H?"),
                )
            )
        self._holes_adjusted = True  # JSON holes are already relative

    def load_from_json_file(self, json_file: str):
        """Load board specifications from a JSON file."""
        with open(json_file, "r") as f:
            data = json.load(f)
        self.load_from_json(data)

    @property
    def frame_width(self) -> float:
        """Calculate frame width including margins."""
        width, _ = self.get_dimensions()
        return width + (2 * self.margin)

    @property
    def frame_height(self) -> float:
        """Calculate frame height including margins."""
        _, height = self.get_dimensions()
        return height + (2 * self.margin)

    @property
    def mounting_holes(self) -> List[Hole]:
        """Alias for get_holes() for backward compatibility."""
        return self.get_holes()

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
        if (
            not self._holes_adjusted
            and self.min_x is not None
            and self.min_y is not None
        ):
            for hole in self.holes:
                hole.x -= self.min_x
                hole.y -= self.min_y
                if self.verbose:
                    self._debug(
                        f"Adjusted hole {hole.reference} to relative coordinates: ({hole.x:.2f}, {hole.y:.2f})"
                    )
            self._holes_adjusted = True
        return self.holes


def normalize_filename(filename: str) -> str:
    """Convert filename to valid OpenSCAD module name.
    Only letters, numbers and underscores allowed.
    Starts with underscore if filename starts with number."""

    if filename.lower().startswith(("http://", "https://")):
        base = os.path.splitext(filename.split("/")[-1])[0]
    else:
        base = os.path.splitext(os.path.basename(filename))[0]

    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", base)

    if normalized[0].isdigit():
        normalized = "_" + normalized

    return normalized


def convert_github_url(url: str) -> str:
    """Convert GitHub web URLs to raw content URLs"""
    if "github.com" in url and "/blob/" in url:
        return url.replace("github.com", "raw.githubusercontent.com").replace(
            "/blob/", "/"
        )
    return url


def fetch_url(url: str) -> str:
    """Fetch content from URL and return as string"""
    try:
        url = convert_github_url(url)
        with urllib.request.urlopen(url) as response:
            return response.read().decode("utf-8")
    except Exception as e:
        print(f"Error fetching URL: {e}")
        print(
            "For GitHub files, make sure you're using the URL from the 'Raw' button view"
        )
        sys.exit(1)


def read_json_pcb(json_file: str) -> Tuple[float, float, List[Hole]]:
    """Read PCB dimensions and mounting holes from JSON file or URL."""
    try:
        if json_file.lower().startswith(("http://", "https://")):
            data = json.loads(fetch_url(json_file))
        else:
            with open(json_file, "r") as f:
                data = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format")
        sys.exit(1)

    if "width" not in data or "height" not in data or "mounting_holes" not in data:
        print("Error: JSON file must contain 'width', 'height', and 'mounting_holes'")
        sys.exit(1)

    width = float(data["width"])
    height = float(data["height"])
    holes = []

    for hole_data in data["mounting_holes"]:
        if "x" not in hole_data or "y" not in hole_data or "diameter" not in hole_data:
            print("Error: Each mounting hole must have 'x', 'y', and 'diameter'")
            sys.exit(1)

        holes.append(
            Hole(
                x=float(hole_data["x"]),
                y=float(hole_data["y"]),
                diameter=float(hole_data["diameter"]),
                reference=hole_data.get("reference", "H?"),
            )
        )

    return width, height, holes


def get_pcb_info(
    input_file: str, verbose: bool = False
) -> Tuple[float, float, List[Hole]]:
    """Get PCB information from either KiCAD PCB file, JSON file, or URL"""
    if input_file.lower().startswith(("http://", "https://")):
        if input_file.lower().endswith(".json"):
            return read_json_pcb(input_file)
        else:
            content = fetch_url(input_file)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".kicad_pcb", delete=False
            ) as tmp:
                tmp.write(content)
                tmp_name = tmp.name
            try:
                framer = Framer(tmp_name, verbose=verbose)
                width, height = framer.get_dimensions()
                holes = framer.get_holes()
                return width, height, holes
            finally:
                os.unlink(tmp_name)
    elif input_file.lower().endswith(".json"):
        return read_json_pcb(input_file)
    else:
        framer = Framer(input_file, verbose=verbose)
        width, height = framer.get_dimensions()
        holes = framer.get_holes()
        return width, height, holes


def calculate_base_dimensions(
    pcb_width: float, pcb_height: float, holes: List[Hole], margin: float
) -> dict:
    """Calculate base dimensions to fit between mounting holes on the smallest side."""
    frame_width = pcb_width + (2 * margin)
    frame_height = pcb_height + (2 * margin)

    adjusted_holes = [(h.x + margin, h.y + margin, h.diameter) for h in holes]

    if frame_width <= frame_height:
        x_positions = sorted(set(h[0] for h in adjusted_holes))
        if len(x_positions) >= 2:
            inner_left = min(x_positions)
            inner_right = max(x_positions)
            hole_diameters_at_edges = [
                h[2] for h in adjusted_holes if h[0] in (inner_left, inner_right)
            ]
            max_hole_dia = (
                max(hole_diameters_at_edges) if hole_diameters_at_edges else 3.0
            )
            base_width = (inner_right - inner_left) - max_hole_dia - 2.0
            base_x_offset = inner_left + (max_hole_dia / 2) + 1.0
        else:
            base_width = frame_width * 0.5
            base_x_offset = frame_width * 0.25

        base_depth = frame_height - 4.0
        base_y_offset = 2.0
        orientation = "width"
    else:
        y_positions = sorted(set(h[1] for h in adjusted_holes))
        if len(y_positions) >= 2:
            inner_bottom = min(y_positions)
            inner_top = max(y_positions)
            hole_diameters_at_edges = [
                h[2] for h in adjusted_holes if h[1] in (inner_bottom, inner_top)
            ]
            max_hole_dia = (
                max(hole_diameters_at_edges) if hole_diameters_at_edges else 3.0
            )
            base_depth = (inner_top - inner_bottom) - max_hole_dia - 2.0
            base_y_offset = inner_bottom + (max_hole_dia / 2) + 1.0
        else:
            base_depth = frame_height * 0.5
            base_y_offset = frame_height * 0.25

        base_width = frame_width - 4.0
        base_x_offset = 2.0
        orientation = "height"

    return {
        "width": max(base_width, 10.0),
        "depth": max(base_depth, 10.0),
        "x_offset": base_x_offset,
        "y_offset": base_y_offset,
        "orientation": orientation,
        "frame_width": frame_width,
        "frame_height": frame_height,
    }


def generate_scad(
    input_file: str,
    frame_thickness: float = 2.0,
    peg_height: float = 6.0,
    margin: float = 2.0,
    use_pegs: bool = False,
    generate_base: bool = False,
    lip_height: float = 5.0,
    base_thickness: float = 2.0,
    verbose: bool = False,
    output_file: Optional[str] = None,
) -> str:
    """Generate OpenSCAD file for PCB frame with mounting holes or pegs.

    Args:
        input_file: Path to KiCAD PCB file, JSON file, or URL
        frame_thickness: Thickness of the base frame in mm (default: 2mm)
        peg_height: Height of the mounting pegs in mm (default: 6mm, only used if use_pegs=True)
        margin: Extra space around PCB edge in mm (default: 2mm)
        use_pegs: If True, generate pegs instead of holes (default: False)
        generate_base: If True, also generate a base to hold the frame (default: False)
        lip_height: Height of the lip on the base in mm (default: 5mm)
        base_thickness: Thickness of the base plate in mm (default: 2mm)
        verbose: Enable verbose output (default: False)
        output_file: Output filename (default: derived from input filename)

    Returns:
        Path to generated OpenSCAD file
    """
    pcb_width, pcb_height, holes = get_pcb_info(input_file, verbose=verbose)

    if not holes:
        print("Error: No mounting holes found in input file")
        sys.exit(1)

    frame_width = pcb_width + (2 * margin)
    frame_height = pcb_height + (2 * margin)

    module_name = normalize_filename(input_file)

    if output_file:
        scad_file = output_file
    else:
        scad_file = f"{module_name}.scad"

    scad_code = f"""// Generated frame for {os.path.basename(input_file)}
// PCB dimensions: {pcb_width:.2f}mm x {pcb_height:.2f}mm
// Frame dimensions: {frame_width:.2f}mm x {frame_height:.2f}mm
// Frame thickness: {frame_thickness:.2f}mm
"""

    if use_pegs:
        scad_code += f"// Peg height: {peg_height:.2f}mm\n"

    scad_code += f"""// Margin around PCB: {margin:.2f}mm

// PCB dimensions as variables
{module_name}_width = {pcb_width:.2f};
{module_name}_depth = {pcb_height:.2f};

// Frame parameters
{module_name}_frame_thickness = {frame_thickness:.2f};  // mm
"""

    if use_pegs:
        scad_code += f"{module_name}_peg_height = {peg_height:.2f};  // mm\n"

    scad_code += f"""
module {module_name}() {{
    difference() {{
        // Base frame
        union() {{
            // Main surface
            translate([0, 0, 0])
                cube([{frame_width:.2f}, {frame_height:.2f}, {module_name}_frame_thickness]);
"""

    min_peg_spacing = 5.0

    if use_pegs:
        for hole in holes:
            x = hole.x + margin
            y = hole.y + margin
            peg_diameter = hole.diameter * 0.9
            scad_code += f"""
            // Mounting peg for {hole.reference}
            translate([{x:.2f}, {y:.2f}, 0]) {{
                cylinder(h={module_name}_frame_thickness + {module_name}_peg_height, d={peg_diameter:.2f}, $fn=32);
            }}"""

        scad_code += f"""
        }}
        
        // Interior cutout
        translate([{margin + min_peg_spacing}, {margin + min_peg_spacing}, -1]) {{
            cube([{frame_width - (2 * (margin + min_peg_spacing))}, {frame_height - (2 * (margin + min_peg_spacing))}, {module_name}_frame_thickness + 2]);
        }}
    }}
}}"""
    else:
        scad_code += """
        }
"""
        for hole in holes:
            x = hole.x + margin
            y = hole.y + margin
            scad_code += f"""
        // Mounting hole for {hole.reference}
        translate([{x:.2f}, {y:.2f}, -1]) {{
            cylinder(h={module_name}_frame_thickness + 2, d={hole.diameter:.2f}, $fn=32);
        }}"""

        scad_code += """
    }
}"""

    if generate_base:
        base_dims = calculate_base_dimensions(pcb_width, pcb_height, holes, margin)
        wall_thickness = 3.0
        notch_width = frame_thickness + 0.3
        wall_height = lip_height

        scad_code += f"""

// Base to hold the frame
// Base dimensions: {base_dims['width']:.2f}mm x {base_dims['depth']:.2f}mm
// Wall height: {wall_height:.2f}mm
// Notch width (gap for frame): {notch_width:.2f}mm

module {module_name}_base() {{
    wall_thickness = {wall_thickness:.2f};
    notch_width = {notch_width:.2f};  // Gap between walls = frame thickness + clearance
    
    // Base plate
    cube([{base_dims['width']:.2f}, {base_dims['depth']:.2f}, {base_thickness:.2f}]);
    
    // Two parallel walls with a gap (notch) between them for the frame to slot into
    // First wall
    translate([0, 0, {base_thickness:.2f}])
        cube([{base_dims['width']:.2f}, wall_thickness, {wall_height:.2f}]);
    
    // Second wall (with notch_width gap from first wall)
    translate([0, wall_thickness + notch_width, {base_thickness:.2f}])
        cube([{base_dims['width']:.2f}, wall_thickness, {wall_height:.2f}]);
}}

// Angled version - walls tilted back 15 degrees
module {module_name}_base_angled() {{
    wall_thickness = {wall_thickness:.2f};
    notch_width = {notch_width:.2f};
    angle = 15;
    wall_height = {wall_height:.2f};
    
    // Calculate how far the top of the wall moves back when angled
    lean_back = wall_height * sin(angle);
    
    // Base plate
    cube([{base_dims['width']:.2f}, {base_dims['depth']:.2f}, {base_thickness:.2f}]);
    
    // Two parallel angled walls with a gap (notch) between them
    // Using hull() to create solid wedge shapes that sit flat on base
    translate([0, 0, {base_thickness:.2f}]) {{
        // First wall - solid wedge leaning back
        hull() {{
            // Bottom edge - flat on base
            cube([{base_dims['width']:.2f}, wall_thickness, 0.01]);
            // Top edge - shifted back
            translate([0, lean_back, wall_height - 0.01])
                cube([{base_dims['width']:.2f}, wall_thickness, 0.01]);
        }}
        
        // Second wall - same angle, with notch gap
        translate([0, wall_thickness + notch_width, 0]) {{
            hull() {{
                // Bottom edge - flat on base
                cube([{base_dims['width']:.2f}, wall_thickness, 0.01]);
                // Top edge - shifted back
                translate([0, lean_back, wall_height - 0.01])
                    cube([{base_dims['width']:.2f}, wall_thickness, 0.01]);
            }}
        }}
    }}
}}
"""

    scad_code += f"""

// Set to 0 when including this file in another project
create_default = 1;  // Set to 0 to prevent auto-creation when included

// Create an instance only if requested
if (create_default) {{
    {module_name}();
"""

    if generate_base:
        base_dims = calculate_base_dimensions(pcb_width, pcb_height, holes, margin)
        scad_code += f"""    
    // Base positioned next to frame for printing
    translate([{frame_width + 5:.2f}, 0, 0])
        {module_name}_base();
    
    // Angled base positioned next to regular base
    translate([{frame_width + base_dims['width'] + 10:.2f}, 0, 0])
        {module_name}_base_angled();
"""

    scad_code += "}\n"

    with open(os.path.basename(scad_file), "w") as f:
        f.write(scad_code)

    print(f"Generated OpenSCAD file: {os.path.basename(scad_file)}")
    return os.path.basename(scad_file)


def main():
    """Command-line entry point for framer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate 3D-printable frames for PCBs from KiCAD files or JSON specifications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  framer board.kicad_pcb              Generate frame with mounting holes
  framer -p board.kicad_pcb           Generate frame with mounting pegs
  framer -b board.kicad_pcb           Generate frame with a base stand
  framer board.json                   Generate frame from JSON specification
  framer https://example.com/board.kicad_pcb  Generate frame from URL

JSON format:
  {
    "width": 50.0,
    "height": 30.0,
    "mounting_holes": [
      {"x": 2.5, "y": 2.5, "diameter": 3.0, "reference": "H1"}
    ]
  }
""",
    )

    parser.add_argument(
        "input_file", help="KiCAD PCB file (.kicad_pcb), JSON file (.json), or URL"
    )
    parser.add_argument("-o", "--output", help="Output OpenSCAD filename")
    parser.add_argument(
        "-t",
        "--thickness",
        type=float,
        default=2.0,
        help="Frame thickness in mm (default: 2.0)",
    )
    parser.add_argument(
        "-m",
        "--margin",
        type=float,
        default=2.0,
        help="Margin around PCB in mm (default: 2.0)",
    )
    parser.add_argument(
        "-p",
        "--pegs",
        nargs="?",
        type=float,
        const=6.0,
        default=None,
        help="Use pegs instead of holes, optionally specify height in mm (default: 6.0)",
    )
    parser.add_argument(
        "-b",
        "--base",
        action="store_true",
        help="Generate a base stand to hold the frame",
    )
    parser.add_argument(
        "--lip-height",
        type=float,
        default=5.0,
        help="Height of base lip in mm (default: 5.0)",
    )
    parser.add_argument(
        "--base-thickness",
        type=float,
        default=2.0,
        help="Thickness of base plate in mm (default: 2.0)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug output"
    )
    parser.add_argument(
        "-i",
        "--info",
        action="store_true",
        help="Only show PCB info (dimensions and holes), do not generate SCAD",
    )

    args = parser.parse_args()

    if args.info:
        try:
            pcb_width, pcb_height, holes = get_pcb_info(
                args.input_file, verbose=args.verbose
            )
            print(f"\nPCB Dimensions: {pcb_width:.2f}mm x {pcb_height:.2f}mm")
            print("\nMounting holes found:")
            for hole in holes:
                print(
                    f"  - {hole.reference}: ({hole.x:.2f}mm, {hole.y:.2f}mm) diameter: {hole.diameter}mm"
                )
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        use_pegs = args.pegs is not None
        peg_height = args.pegs if args.pegs else 6.0

        generate_scad(
            input_file=args.input_file,
            frame_thickness=args.thickness,
            peg_height=peg_height,
            margin=args.margin,
            use_pegs=use_pegs,
            generate_base=args.base,
            lip_height=args.lip_height,
            base_thickness=args.base_thickness,
            verbose=args.verbose,
            output_file=args.output,
        )


if __name__ == "__main__":
    main()
