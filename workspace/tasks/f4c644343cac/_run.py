import numpy as np

# Given parameters
L = 200  # length in meters
D = 0.15  # diameter in meters
v = 2  # velocity in m/s
f = 0.02  # friction factor
rho = 1000  # density in kg/m³

# Step 1: Calculate L/D
L_over_D = L / D
print(f'L/D = {L_over_D:.2f} (200 / 0.15)')

# Step 2: Multiply by friction factor
f_L_over_D = f * L_over_D
print(f'f*(L/D) = {f_L_over_D:.4f} (0.02 * {L_over_D:.2f})')

# Step 3: Calculate velocity squared term
velocity_squared_term = (rho * v**2) / 2
print(f'ρ*v²/2 = {velocity_squared_term:.0f} (1000 * 2² / 2)')

# Step 4: Multiply all terms for ΔP
delta_P = f_L_over_D * velocity_squared_term
print(f'ΔP = {delta_P:.2f} Pa (f*(L/D) * ρ*v²/2)')

# Convert to kPa
delta_P_kPa = delta_P / 1000
print(f'ΔP = {delta_P_kPa:.2f} kPa')