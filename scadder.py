#!/usr/bin/env python3

import sys
import os
import re
import json
import urllib.request
from framer import Framer, Hole

def normalize_filename(filename: str) -> str:
    """Convert filename to valid OpenSCAD module name.
    Only letters, numbers and underscores allowed.
    Starts with underscore if filename starts with number."""
    
    # Remove extension and path
    if filename.lower().startswith(('http://', 'https://')):
        # For URLs, use the last part of the path
        base = os.path.splitext(filename.split('/')[-1])[0]
    else:
        base = os.path.splitext(os.path.basename(filename))[0]
    
    # Replace any non-alphanumeric chars with underscore
    normalized = re.sub(r'[^a-zA-Z0-9_]', '_', base)
    
    # Ensure starts with letter or underscore
    if normalized[0].isdigit():
        normalized = '_' + normalized
        
    return normalized

def convert_github_url(url: str) -> str:
    """Convert GitHub web URLs to raw content URLs"""
    if 'github.com' in url and '/blob/' in url:
        # Convert https://github.com/owner/repo/blob/branch/path
        # to     https://raw.githubusercontent.com/owner/repo/branch/path
        return url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
    return url

def fetch_url(url: str) -> str:
    """Fetch content from URL and return as string"""
    try:
        # Convert GitHub URLs to raw content URLs
        url = convert_github_url(url)
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching URL: {e}")
        print("For GitHub files, make sure you're using the URL from the 'Raw' button view")
        sys.exit(1)

def read_json_pcb(json_file: str) -> tuple[float, float, list[Hole]]:
    """Read PCB dimensions and mounting holes from JSON file or URL.
    
    Expected JSON format:
    {
        "width": float,      # PCB width in mm
        "height": float,     # PCB height in mm
        "mounting_holes": [  # List of mounting holes
            {
                "x": float,      # X coordinate from left edge in mm
                "y": float,      # Y coordinate from top edge in mm
                "diameter": float,# Hole diameter in mm
                "reference": str  # Reference designator (optional)
            },
            ...
        ]
    }
    """
    try:
        if json_file.lower().startswith(('http://', 'https://')):
            data = json.loads(fetch_url(json_file))
        else:
            with open(json_file, 'r') as f:
                data = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format")
        sys.exit(1)
        
    # Validate required fields
    if 'width' not in data or 'height' not in data or 'mounting_holes' not in data:
        print("Error: JSON file must contain 'width', 'height', and 'mounting_holes'")
        sys.exit(1)
        
    width = float(data['width'])
    height = float(data['height'])
    holes = []
    
    for hole_data in data['mounting_holes']:
        if 'x' not in hole_data or 'y' not in hole_data or 'diameter' not in hole_data:
            print("Error: Each mounting hole must have 'x', 'y', and 'diameter'")
            sys.exit(1)
            
        holes.append(Hole(
            x=float(hole_data['x']),
            y=float(hole_data['y']),
            diameter=float(hole_data['diameter']),
            reference=hole_data.get('reference', 'H?')  # Default reference if not specified
        ))
        
    return width, height, holes

def get_pcb_info(input_file: str) -> tuple[float, float, list[Hole]]:
    """Get PCB information from either KiCAD PCB file, JSON file, or URL"""
    if input_file.lower().startswith(('http://', 'https://')):
        # For URLs, check the file extension
        if input_file.lower().endswith('.json'):
            return read_json_pcb(input_file)
        else:
            # For KiCAD files, save to a temporary file
            content = fetch_url(input_file)
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.kicad_pcb', delete=False) as tmp:
                tmp.write(content)
                tmp_name = tmp.name
            try:
                framer = Framer(tmp_name)
                width, height = framer.get_dimensions()
                holes = framer.get_holes()
                return width, height, holes
            finally:
                os.unlink(tmp_name)  # Clean up temporary file
    elif input_file.lower().endswith('.json'):
        return read_json_pcb(input_file)
    else:
        framer = Framer(input_file)
        width, height = framer.get_dimensions()
        holes = framer.get_holes()
        return width, height, holes

def generate_scad(input_file: str, frame_thickness: float = 2.0, peg_height: float = 6.0, margin: float = 2.0, use_pegs: bool = False):
    """Generate OpenSCAD file for PCB frame with mounting holes or pegs
    
    Args:
        input_file: Path to KiCAD PCB file or JSON file
        frame_thickness: Thickness of the base frame in mm (default: 2mm)
        peg_height: Height of the mounting pegs in mm (default: 6mm, only used if use_pegs=True)
        margin: Extra space around PCB edge in mm (default: 2mm)
        use_pegs: If True, generate pegs instead of holes (default: False)
    """
    
    # Get PCB info from either KiCAD or JSON file
    pcb_width, pcb_height, holes = get_pcb_info(input_file)
    
    if not holes:
        print("Error: No mounting holes found in input file")
        sys.exit(1)
    
    # Calculate frame dimensions (slightly larger than PCB)
    frame_width = pcb_width + (2 * margin)
    frame_height = pcb_height + (2 * margin)
    
    # Create normalized module name
    module_name = normalize_filename(input_file)
    
    # Create output filename in current directory
    scad_file = f"{module_name}.scad"
    
    # Generate OpenSCAD code
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

    # Add mounting features (pegs or holes)
    min_peg_spacing = 5.0  # Minimum material around peg for support
    
    if use_pegs:
        for hole in holes:
            # Adjust hole coordinates for margin
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
            # Adjust hole coordinates for margin
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
    
    scad_code += f"""

// Set to 0 when including this file in another project
create_default = 1;  // Set to 0 to prevent auto-creation when included

// Create an instance only if requested
if (create_default) {{
    {module_name}();
}}
"""
    
    # Write to file in current directory
    with open(os.path.basename(scad_file), 'w') as f:
        f.write(scad_code)
        
    print(f"Generated OpenSCAD file: {os.path.basename(scad_file)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: scadder.py <kicad_pcb_file|json_file> [frame_thickness_mm] [margin_mm] [-p|--pegs [peg_height_mm]]")
        sys.exit(1)
        
    frame_thickness = 2.0  # default frame thickness
    peg_height = 6.0      # default peg height
    margin = 2.0          # default margin around PCB
    use_pegs = False      # default to holes
    
    # Parse arguments
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ['-p', '--pegs']:
            use_pegs = True
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('-'):
                try:
                    peg_height = float(sys.argv[i + 1])
                    i += 1
                except ValueError:
                    print("Error: peg height must be a number in mm")
                    sys.exit(1)
        elif i <= 3:  # First two optional args are frame_thickness and margin
            try:
                if i == 2:
                    frame_thickness = float(arg)
                else:
                    margin = float(arg)
            except ValueError:
                print(f"Error: {'frame thickness' if i == 2 else 'margin'} must be a number in mm")
                sys.exit(1)
        i += 1
            
    generate_scad(sys.argv[1], frame_thickness, peg_height, margin, use_pegs) 