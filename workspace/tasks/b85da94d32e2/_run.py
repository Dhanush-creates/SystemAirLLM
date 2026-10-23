import numpy as np

# Given parameters
length = 200  # m
friction_factor = 0.02
velocity = 2  # m/s
density = 1000  # kg/m3
diameter = 0.15  # m

# Calculate the friction loss
friction_loss = friction_factor * (length / diameter) * (velocity ** 2) / 2

# Calculate the pressure drop
pressure_drop = friction_loss * density

print(f'Friction loss = {friction_loss} m (friction_factor * (length / diameter) * (velocity ** 2) / 2)')
print(f'Pressure drop = {pressure_drop} Pa (friction_loss * density)')