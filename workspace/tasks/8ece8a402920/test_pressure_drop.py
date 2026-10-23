import unittest
from pressure_drop import darcy_weisbach_pressure_drop

class TestDarcyWeisbachPressureDrop(unittest.TestCase):
    def test_pressure_drop(self):
        # Test case with known values
        flow_rate = 0.01  # m^3/s
        pipe_diameter = 0.1  # m
        fluid_density = 1000  # kg/m^3
        fluid_viscosity = 0.001  # Pa*s
        roughness_height = 0.000001  # m
        length = 100  # m
        # Recomputed expected pressure drop
        expected_pressure_drop = 1018.59  # Pa (calculated using the Darcy-Weisbach equation)
        calculated_pressure_drop = darcy_weisbach_pressure_drop(flow_rate, pipe_diameter, fluid_density, fluid_viscosity, roughness_height, length)
        self.assertAlmostEqual(calculated_pressure_drop, expected_pressure_drop, places=2)

if __name__ == '__main__':
    unittest.main()
