def darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor):
    # Darcy-Weisbach equation: ΔP = f * (L/D) * (1/2) * ρ * v^2
    return friction_factor * (length / diameter) * 0.5 * fluid_density * velocity**2

# Example usage:
# print(darcy_weisbach_pressure_drop(1.5, 0.1, 100, 0.00015, 1000, 0.02))