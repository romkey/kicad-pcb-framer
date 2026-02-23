"""Tests for the framer package."""

import unittest
import json
import tempfile
import os
from framer import Framer, Hole, generate_scad


class TestHole(unittest.TestCase):
    """Test the Hole dataclass."""
    
    def test_hole_creation(self):
        """Test creating a Hole object."""
        hole = Hole(x=10.0, y=20.0, diameter=3.0, reference="H1")
        self.assertEqual(hole.x, 10.0)
        self.assertEqual(hole.y, 20.0)
        self.assertEqual(hole.diameter, 3.0)
        self.assertEqual(hole.reference, "H1")


class TestFramerWithJson(unittest.TestCase):
    """Test Framer class with JSON input."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_json = {
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
        
    def test_json_load(self):
        """Test loading board specs from JSON dict."""
        framer = Framer()
        framer.load_from_json(self.test_json)
        
        width, height = framer.get_dimensions()
        self.assertEqual(width, 50.0)
        self.assertEqual(height, 30.0)
        self.assertEqual(len(framer.get_holes()), 2)

    def test_dimensions_properties(self):
        """Test frame dimensions calculation with margin."""
        framer = Framer()
        framer.load_from_json(self.test_json)
        
        self.assertEqual(framer.frame_width, 54.0)  # 50 + (2 * 2)
        self.assertEqual(framer.frame_height, 34.0)  # 30 + (2 * 2)

    def test_custom_margin(self):
        """Test frame dimensions with custom margin."""
        framer = Framer()
        framer.margin = 5.0
        framer.load_from_json(self.test_json)
        
        self.assertEqual(framer.frame_width, 60.0)  # 50 + (2 * 5)
        self.assertEqual(framer.frame_height, 40.0)  # 30 + (2 * 5)

    def test_mounting_holes_alias(self):
        """Test mounting_holes property alias."""
        framer = Framer()
        framer.load_from_json(self.test_json)
        
        self.assertEqual(len(framer.mounting_holes), 2)
        self.assertEqual(framer.mounting_holes[0].reference, "H1")

    def test_hole_coordinates(self):
        """Test hole coordinates are correctly loaded."""
        framer = Framer()
        framer.load_from_json(self.test_json)
        
        holes = framer.get_holes()
        h1 = holes[0]
        h2 = holes[1]
        
        self.assertEqual(h1.x, 2.5)
        self.assertEqual(h1.y, 2.5)
        self.assertEqual(h2.x, 47.5)
        self.assertEqual(h2.y, 27.5)


class TestFramerWithJsonFile(unittest.TestCase):
    """Test Framer class loading from JSON file."""
    
    def test_load_from_json_file(self):
        """Test loading from a JSON file."""
        test_data = {
            "width": 100.0,
            "height": 80.0,
            "mounting_holes": [
                {"x": 5.0, "y": 5.0, "diameter": 3.2, "reference": "MH1"}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name
        
        try:
            framer = Framer()
            framer.load_from_json_file(temp_path)
            
            width, height = framer.get_dimensions()
            self.assertEqual(width, 100.0)
            self.assertEqual(height, 80.0)
            self.assertEqual(len(framer.get_holes()), 1)
        finally:
            os.unlink(temp_path)


class TestGenerateScad(unittest.TestCase):
    """Test OpenSCAD generation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_json = {
            "width": 50.0,
            "height": 30.0,
            "mounting_holes": [
                {"x": 2.5, "y": 2.5, "diameter": 3.0, "reference": "H1"},
                {"x": 47.5, "y": 27.5, "diameter": 3.0, "reference": "H2"}
            ]
        }
        self.temp_json = None
        self.generated_scad = None
    
    def tearDown(self):
        """Clean up temporary files."""
        if self.temp_json and os.path.exists(self.temp_json):
            os.unlink(self.temp_json)
        if self.generated_scad and os.path.exists(self.generated_scad):
            os.unlink(self.generated_scad)
    
    def test_generate_scad_with_holes(self):
        """Test generating SCAD with mounting holes."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.test_json, f)
            self.temp_json = f.name
        
        self.generated_scad = generate_scad(self.temp_json, use_pegs=False)
        
        self.assertTrue(os.path.exists(self.generated_scad))
        with open(self.generated_scad, 'r') as f:
            content = f.read()
        
        self.assertIn('module', content)
        self.assertIn('Mounting hole for H1', content)
        self.assertIn('Mounting hole for H2', content)
        self.assertIn('cylinder', content)
    
    def test_generate_scad_with_pegs(self):
        """Test generating SCAD with mounting pegs."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.test_json, f)
            self.temp_json = f.name
        
        self.generated_scad = generate_scad(self.temp_json, use_pegs=True)
        
        with open(self.generated_scad, 'r') as f:
            content = f.read()
        
        self.assertIn('Mounting peg for H1', content)
        self.assertIn('Peg height', content)
    
    def test_generate_scad_with_base(self):
        """Test generating SCAD with base stand."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.test_json, f)
            self.temp_json = f.name
        
        self.generated_scad = generate_scad(self.temp_json, generate_base=True)
        
        with open(self.generated_scad, 'r') as f:
            content = f.read()
        
        self.assertIn('_base()', content)
        self.assertIn('_base_angled()', content)


class TestFramerNoBoardLoaded(unittest.TestCase):
    """Test Framer behavior when no board is loaded."""
    
    def test_no_dimensions_raises_error(self):
        """Test that get_dimensions raises error when no board loaded."""
        framer = Framer()
        with self.assertRaises(ValueError):
            framer.get_dimensions()


if __name__ == '__main__':
    unittest.main()
