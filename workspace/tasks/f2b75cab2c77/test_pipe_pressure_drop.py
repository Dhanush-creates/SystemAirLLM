import unittest
from pipe_pressure_drop import darcy_weisbach_pressure_drop

class TestDarcyWeisbachPressureDrop(unittest.TestCase):
    def test_pressure_drop(self):
        # Test case with known values
        velocity = 1.5
        diameter = 0.1
        length = 100
        roughness = 0.00015
        fluid_density = 1000
        friction_factor = 0.02
        expected_pressure_drop = 22500.0
        calculated_pressure_drop = darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor)
        self.assertAlmostEqual(calculated_pressure_drop, expected_pressure_drop, places=2)

if __name__ == '__main__':
    unittest.main()