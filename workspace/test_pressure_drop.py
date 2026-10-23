from pressure_drop import darcy_weisbach_pressure_drop

import unittest

class TestDarcyWeisbachPressureDrop(unittest.TestCase):
    def test_pressure_drop(self):
        velocity = 1.0  # m/s
        diameter = 0.1  # m
        length = 100.0  # m
        roughness = 0.0001  # m
        fluid_density = 1000  # kg/m^3
        fluid_viscosity = 0.001  # Pa*s
        expected_pressure_drop = 320000.0  # Pa
        calculated_pressure_drop = darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, fluid_viscosity)
        self.assertAlmostEqual(calculated_pressure_drop, expected_pressure_drop, places=1)

if __name__ == '__main__':
    unittest.main()