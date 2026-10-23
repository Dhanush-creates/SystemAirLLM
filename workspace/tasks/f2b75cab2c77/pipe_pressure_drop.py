def darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor):
    # Darcy-Weisbach equation: ΔP = f * (L/D) * (ρ/2) * v^2
    return friction_factor * (length / diameter) * (fluid_density / 2) * velocity ** 2

# Example usage:
# pressure_drop = darcy_weisbach_pressure_drop(velocity=1.5, diameter=0.1, length=100, roughness=0.00015, fluid_density=1000, friction_factor=0.02)
# print(pressure_drop)