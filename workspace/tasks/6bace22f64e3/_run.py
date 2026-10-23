from pipe_pressure_drop import darcy_weisbach_pressure_drop
velocity = 1.5  # m/s
diameter = 0.1  # m
length = 100    # m
roughness = 0.00015  # m
fluid_density = 1000  # kg/m^3
friction_factor = 0.02
print(darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor))