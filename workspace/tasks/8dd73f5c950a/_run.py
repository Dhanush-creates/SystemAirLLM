import numpy as np

# Given values
f = 0.02  # Friction factor
L = 200  # Length of the pipe in meters
D = 0.15  # Diameter of the pipe in meters
rho = 1000  # Density of water in kg/m3
v = 2  # Velocity of water in m/s

# Calculate pressure drop using Darcy-Weisbach equation
Delta_P = f * (L/D) * (rho * v**2)/2

# Print the result
print(f'Pressure drop (ΔP) = {Delta_P} Pa')