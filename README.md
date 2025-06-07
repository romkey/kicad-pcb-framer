# PCB Frame Generator

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
- Material-saving interior cutout
- Support for direct URLs (including GitHub)

## Installation

```bash
git clone https://github.com/yourusername/pcb-frame-generator.git
cd pcb-frame-generator
```

## Usage

### Basic Usage

```bash
./scadder.py your_board.kicad_pcb
```

This will generate an OpenSCAD file with mounting holes matching your PCB.

### Using Mounting Pegs

```bash
./scadder.py -p your_board.kicad_pcb
```

This generates pegs instead of holes (90% of hole diameter for secure fit).

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
./scadder.py board_spec.json
```

### Using URLs

You can directly use URLs to KiCAD or JSON files:

```bash
./scadder.py https://raw.githubusercontent.com/user/repo/main/board.kicad_pcb
```

GitHub web URLs are automatically converted to raw URLs.

## Files

- `framer.py`: Parses KiCAD PCB files to extract dimensions and mounting holes
- `scadder.py`: Generates OpenSCAD code for the frame

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