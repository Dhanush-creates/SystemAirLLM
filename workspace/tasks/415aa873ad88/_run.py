L = 200
D = 0.15
L_over_D = L / D
print(f'L/D = {L_over_D:.2f}')

v = 2
rho = 1000
velocity_squared = v ** 2
rho_v2_over_2 = (rho * velocity_squared) / 2
print(f'ρ*v²/2 = {rho_v2_over_2} kg/(m·s²)')

f = 0.02
friction_term = f * L_over_D
print(f'f*(L/D) = {friction_term:.4f}')

pressure_drop = friction_term * rho_v2_over_2
print(f'ΔP = {pressure_drop} Pa')