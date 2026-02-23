# Framer - PCB Frame Generator

Generate 3D-printable frames for PCBs from KiCAD files or JSON specifications. The frames can include either mounting holes or pegs to secure your PCB.

## Features

- Supports KiCAD PCB files (.kicad_pcb)
- Supports JSON specification files
- Generates OpenSCAD code for 3D printing
- Configurable frame parameters:
  - Frame thickness (default 2mm)
  - Margin around PCB (default 2mm)
  - Peg height for mounting (default 6mm)
- Option for mounting holes or pegs
- Optional base stand generation (flat or angled)
- Support for direct URLs (including GitHub)

## Installation

### Using pip (NOT YET SUPPORTED)

```bash
pip install framer
```

### From Source

```bash
git clone https://github.com/romkey/kicad-pcb-framer
cd kicad-pcb-framer
pip install -e .
```

## Usage

### Basic Usage

```bash
framer your_board.kicad_pcb
```

This will generate an OpenSCAD file with mounting holes matching your PCB.

### Using Mounting Pegs

```bash
framer -p your_board.kicad_pcb
```

This generates pegs instead of holes (90% of hole diameter for a secure fit).

You can also specify the peg height:

```bash
framer -p 8 your_board.kicad_pcb
```

### Generating a Base Stand

```bash
framer -b your_board.kicad_pcb
```

This generates both the frame and a base stand that holds the frame upright. Two base variants are generated: a flat version and an angled (15°) version.

You can customize the base:

```bash
framer -b --lip-height 8 --base-thickness 3 your_board.kicad_pcb
```

### Custom Frame Parameters

```bash
framer -t 3 -m 4 your_board.kicad_pcb
```

This generates a frame with 3mm thickness and 4mm margin around the PCB.

### Show PCB Info Only

```bash
framer -i your_board.kicad_pcb
```

This displays the PCB dimensions and mounting holes without generating an OpenSCAD file.

### Using JSON Input

You can specify board dimensions and mounting holes in JSON:

```json
{
  "width": 50.0,
  "height": 30.0,
  "mounting_holes": [
    {
      "x": 2.5,
      "y": 2.5,
      "diameter": 3.0,
      "reference": "H1"
    },
    {
      "x": 47.5,
      "y": 27.5,
      "diameter": 3.0,
      "reference": "H2"
    }
  ]
}
```

Then generate the frame:

```bash
framer board_spec.json
```

### Using URLs

You can directly use URLs to KiCAD or JSON files:

```bash
framer https://raw.githubusercontent.com/user/repo/main/board.kicad_pcb
```

GitHub web URLs are automatically converted to raw URLs.

## Command-Line Options

```
usage: framer [-h] [-o OUTPUT] [-t THICKNESS] [-m MARGIN] [-p [PEGS]]
              [-b] [--lip-height LIP_HEIGHT] [--base-thickness BASE_THICKNESS]
              [-v] [-i] input_file

Generate 3D-printable frames for PCBs from KiCAD files or JSON specifications.

positional arguments:
  input_file            KiCAD PCB file (.kicad_pcb), JSON file (.json), or URL

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output OpenSCAD filename
  -t THICKNESS, --thickness THICKNESS
                        Frame thickness in mm (default: 2.0)
  -m MARGIN, --margin MARGIN
                        Margin around PCB in mm (default: 2.0)
  -p [PEGS], --pegs [PEGS]
                        Use pegs instead of holes, optionally specify height
                        in mm (default: 6.0)
  -b, --base            Generate a base stand to hold the frame
  --lip-height LIP_HEIGHT
                        Height of base lip in mm (default: 5.0)
  --base-thickness BASE_THICKNESS
                        Thickness of base plate in mm (default: 2.0)
  -v, --verbose         Enable verbose debug output
  -i, --info            Only show PCB info (dimensions and holes), do not
                        generate SCAD
```

## Python API

You can also use framer as a Python library:

```python
from framer import Framer, generate_scad

# From a KiCAD file
framer = Framer('board.kicad_pcb')
width, height = framer.get_dimensions()
holes = framer.get_holes()

# From JSON
framer = Framer()
framer.load_from_json({
    "width": 50.0,
    "height": 30.0,
    "mounting_holes": [
        {"x": 2.5, "y": 2.5, "diameter": 3.0, "reference": "H1"}
    ]
})

# Generate OpenSCAD file
generate_scad('board.kicad_pcb', use_pegs=True, generate_base=True)
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -am 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Code of Conduct

This project has adopted the [Adafruit Community Code of Conduct](CODE_OF_CONDUCT.md). For more information see the Code of Conduct FAQ at https://www.adafruit.com/coc.
