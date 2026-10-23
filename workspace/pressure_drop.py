def darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, fluid_viscosity):
    from math import sqrt
    reynolds_number = (velocity * diameter) / fluid_viscosity
    if reynolds_number < 2300:
        f = 64 / reynolds_number
    else:
        f = 0.079 / (reynolds_number ** 0.25)
    pressure_drop = (f * length * fluid_density * velocity ** 2) / (2 * diameter)
    return pressure_drop

import unittest

class TestDarcyWeisbachPressureDrop(unittest.TestCase):
    def test_pressure_drop(self):
        velocity = 1.0  # m/s
        diameter = 0.1  # m
        length = 100.0  # m
        roughness = 0.0001  # m
        fluid_density = 1000  # kg/m^3
        fluid_viscosity = 0.001  # Pa*s
        expected_pressure_drop = 196.0  # Pa
        calculated_pressure_drop = darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, fluid_viscosity)
        self.assertAlmostEqual(calculated_pressure_drop, expected_pressure_drop, places=1)

if __name__ == '__main__':
    unittest.main()