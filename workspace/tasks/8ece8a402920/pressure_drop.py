def darcy_weisbach_pressure_drop(flow_rate, pipe_diameter, fluid_density, fluid_viscosity, roughness_height, length):
    # Constants
    g = 9.81  # acceleration due to gravity (m/s^2)
    # Darcy-Weisbach friction factor (using the Colebrook-White equation)
    Re = (flow_rate * pipe_diameter) / (fluid_viscosity * 3.14159)
    if Re < 2300:
        f = 64 / Re
    else:
        f = 0.25 / (2.51 * (math.log10((roughness_height / pipe_diameter) + (2.51 / (Re ** 0.9)))) ** 2)
    # Pressure drop calculation
    pressure_drop = (f * length * fluid_density * (flow_rate ** 2)) / (2 * pipe_diameter * 3.14159 ** 2)
    return pressure_drop

import math
