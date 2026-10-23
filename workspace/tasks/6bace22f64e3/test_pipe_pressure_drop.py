import unittest
from pipe_pressure_drop import darcy_weisbach_pressure_drop

class TestDarcyWeisbachPressureDrop(unittest.TestCase):
    def test_pressure_drop(self):
        # Test case with known values
        velocity = 1.5  # m/s
        diameter = 0.1  # m
        length = 100    # m
        roughness = 0.00015  # m
        fluid_density = 1000  # kg/m^3
        friction_factor = 0.02
        expected_pressure_drop = 22500.0  # Pa
        self.assertAlmostEqual(darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor), expected_pressure_drop, places=2)

if __name__ == '__main__':
    unittest.main()