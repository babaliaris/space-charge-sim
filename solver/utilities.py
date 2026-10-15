import numpy as np
from scipy.integrate import quad
from solver.constants import EPSILON_0

def impulse_voltage(t, V_peak, alpha, beta, k=1.0):
    """
    Calculates instantaneous impulse voltage V(t) for a double-exponential wave.
    V(t) = Vp * k * ( e^{-at} - e^{-bt} )
    """
    return V_peak * k * ( np.exp(-alpha * t) - np.exp(-beta * t) )


def double_exponential_parameters(t_crest, t_half):
    """
    Finds alpha, beta [1/s] and k of impulse_voltage() from the usual HV description
    of the waveform, so that V(t) reaches exactly V_peak at t_crest:

    t_crest : time to crest [s]                (e.g. 100e-6 for a 100 us wavefront)
    t_half  : time to half value on the tail [s] (e.g. 2500e-6)

    Returns (alpha, beta, k).
    """
    from scipy.optimize import brentq, fsolve

    def crest_time(alpha, beta):          # dV/dt = 0
        return np.log(beta / alpha) / (beta - alpha)

    def k_factor(alpha, beta):            # makes the crest equal to V_peak
        t = crest_time(alpha, beta)
        return 1.0 / (np.exp(-alpha * t) - np.exp(-beta * t))

    def mismatch(log_params):
        alpha, beta = np.exp(log_params)  # logs keep both rates positive
        k = k_factor(alpha, beta)
        t_c = crest_time(alpha, beta)
        half = brentq(lambda t: k * (np.exp(-alpha * t) - np.exp(-beta * t)) - 0.5, t_c, 100.0 * t_half)
        return [t_c / t_crest - 1.0, half / t_half - 1.0]

    alpha, beta = np.exp(fsolve(mismatch, [np.log(0.7 / t_half), np.log(5.0 / t_crest)], xtol=1e-12))
    return alpha, beta, k_factor(alpha, beta)




def calculate_qcs_from_field(E_c_v_m: float, L_cs_m: float, theta_B_rad: float) -> float:
    """
    Calculates the total streamer space charge Q_cs (in Coulombs) based on
    Gauss's Law and the average streamer field E_c.

    Parameters:
    ----------
    E_c_v_m     : Average electric field in the streamer region [V/m] (typically ~5e5 = 5 kV/cm)
    L_cs_m      : Streamer development length [meters]
    theta_B_rad : Total cone boundary angle [radians] (half-angle is theta_B / 2)

    Returns:
    -------
    Q_cs : Total space charge [Coulombs]
    """
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

