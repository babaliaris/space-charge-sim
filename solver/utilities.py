import numpy as np
from scipy.integrate import quad
from solver.constants import EPSILON_0

def impulse_voltage(t, V_peak, alpha, beta, k=1.0):
    """
    Calculates instantaneous impulse voltage V(t) for a double-exponential wave.
    V(t) = Vp * k * ( e^{-at} - e^{-bt} )
    """
    return V_peak * k * ( np.exp(-alpha * t) - np.exp(-beta * t) )




def calculate_qcs_from_field(E_c_kv_cm: float, L_cs_m: float, theta_B_rad: float) -> float:
    """
    Calculates the total streamer space charge Q_cs (in Coulombs) based on
    Gauss's Law and the average streamer field E_c.

    Parameters:
    ----------
    E_c_kv_cm   : Average electric field in the streamer region [kV/cm] (typically ~5.0)
    L_cs_m      : Streamer development length [meters]
    theta_B_rad : Total cone boundary angle [radians] (half-angle is theta_B / 2)

    Returns:
    -------
    Q_cs : Total space charge [Coulombs]
    """
    # Convert kV/cm to V/m (1 kV/cm = 100,000 V/m)
    E_c_v_m = E_c_kv_cm * 1e5

    # Radius of the conical streamer head at distance L_cs
    half_angle = theta_B_rad / 2.0
    r_head = L_cs_m * np.tan(half_angle)

    # Cross-sectional boundary area at the streamer tip
    area_head = np.pi * (r_head**2)

    # Enclosed charge Q_cs from Gauss's Law
    Q_cs = EPSILON_0 * E_c_v_m * area_head
    return Q_cs




def calculate_A_from_charge(
    Q_cs        : float,
    B           : float,
    C_m         : float,
    L_cs_m      : float,
    theta_B_rad : float
) -> float:
    """
    Calculates the charge density amplitude constant 'A' by inverting the 3D
    volume integral of the charge distribution rho(r) = A / (r + C)^B.

    Parameters:
    ----------
    Q_cs        : Total streamer charge [Coulombs]
    B           : Decay exponent parameter (dimensionless, typically 1.5)
    C_m         : Characteristic decay radius [meters] (typically 0.00035 m = 0.035 cm)
    L_cs_m      : Streamer development length [meters]
    theta_B_rad : Total cone boundary angle [radians]
    R_m         : Electrode rod apex radius [meters]

    Returns:
    -------
    A : Amplitude parameter in SI units [C * m^(B - 3)]
    """
    half_angle = theta_B_rad / 2.0

    # Integrated solid angle for cone: Omega = 2 * pi * (1 - cos(theta_B / 2))
    solid_angle = 2.0 * np.pi * (1.0 - np.cos(half_angle))

    # Integrand for the radial component (r measured from electrode tip)
    def radial_integrand(r):
        return (r**2) / ((r + C_m)**B)

    # Compute definite integral from tip surface (r = 0) to streamer end (r = L_cs)
    integral_val, _ = quad(radial_integrand, 0.0, L_cs_m)

    # Invert Q_cs = A * solid_angle * integral_val
    A = Q_cs / (solid_angle * integral_val)
    return A































































