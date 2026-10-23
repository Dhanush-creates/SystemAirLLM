from pipe_pressure_drop import darcy_weisbach_pressure_drop
velocity = 1.5
diameter = 0.1
length = 100
roughness = 0.00015
fluid_density = 1000
friction_factor = 0.02
expected_pressure_drop = darcy_weisbach_pressure_drop(velocity, diameter, length, roughness, fluid_density, friction_factor)
print(expected_pressure_drop)