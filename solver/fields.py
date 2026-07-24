import numpy as np
from scipy.integrate import dblquad
from solver.constants import EPSILON_0

def charge_density(r, A, B, C):
    """
    Calculates space charge density rho(r) = A / (r + C)^B
    Vectorized: works for a single scalar r or a NumPy array of r values.
    """
    return A / np.power(r + C, B)



def _esp_integrand(r, theta, z, R, A, B, C):
    """
    Evaluates the scalar integrand of E_sp at a single point (r, theta).
    f(r,θ)  =  [ ρ(r) * r^2 sin(θ) * dz ] / r1^3
    dz      = z - R - rcos(θ)
    r1      = sqrt( dz^2 * [ rsin(θ) ]^2 )
    """
    dz = z - R - r * np.cos(theta)
    r1 = np.sqrt( dz**2 + (r * np.sin(theta))**2 )

    # Safeguard against division by zero if an evaluation point hits a singular charge point
    if r1 == 0:
        return 0.0

    rho = charge_density(r, A, B, C)

    return (rho * (r**2) * np.sin(theta) * dz) / (r1**3)

def _e_rod_image_integrand(r, theta, z, R, A, B, C):
    """
    Evaluates the scalar integrand of E_{I_rod} at a single point (r, theta).
    """
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # 1. Distance from spherical center O to source charge element
    r2 = np.sqrt((R + r * cos_t)**2 + (r * sin_t)**2)
    if r2 == 0:
        return 0.0

    # 2. Distance of Kelvin image charge from center O
    r3 = (R**2) / r2

    # Ratio used in image charge coordinate projections
    scale = r3 / r2

    # 3. Axial displacement between field point z and image charge point
    dz_image = z - scale * (R + r * cos_t)

    # 4. Scalar distance r4 from image charge element to field point
    r4 = np.sqrt(dz_image**2 + (scale * r * sin_t)**2)
    if r4 == 0:
        return 0.0

    # 5. Charge density at r
    rho = charge_density(r, A, B, C)

    # Integrand: (rho * r^2 * R * sin(theta) / (r4^3 * r2)) * dz_image
    numerator = rho * (r**2) * R * sin_t * dz_image
    denominator = (r4**3) * r2

    return numerator / denominator


def calculate_e_sp(z, R, L_cs, theta_B, A, B, C, epsilon_r=1.0, epsabs=1e-8, epsrel=1e-8):
    """
    Calculates the axial direct space charge field E_sp(z).
    
    Parameters:
    -----------
    z : float or np.ndarray
        Observation point(s) along the symmetry axis [m].
    R : float
        Rod tip radius [m].
    L_cs : float
        Length of space charge region [m].
    theta_B : float
        Total cone boundary angle [rad].
    A, B, C : float
        Parameters for charge density rho(r) = A * (r + C)^B.
    epsilon_r : float
        Relative permittivity of ambient medium (default = 1.0 for air).
    epsabs, epsrel : float
        Absolute and relative error tolerances for adaptive quadrature.
        
    Returns:
    --------
    E_sp : float or np.ndarray
        Direct space-charge electric field magnitude [V/m].
    """
    coeff       = 1.0 / (2.0 * epsilon_r * EPSILON_0)
    theta_max   = theta_B / 2.0

    # If z is an array of observation points, compute field point-by-point
    z_arr           = np.atleast_1d(z)
    e_sp_results    = np.zeros_like(z_arr, dtype=float)

    # For each observation point, calculate Esp(0,0,z) value.
    for i, z_val in enumerate(z_arr):
        # dblquad integration over r in [0, L_cs] and theta in [0, theta_B/2]
        res = dblquad(
            _esp_integrand,
            0.0, theta_max,                 # Outer integral limits (theta)
            lambda _: 0.0,  lambda _: L_cs, # Inner limits r(theta)
            args=(z_val, R, A, B, C),       # Extra arguments passed to _esp_integrand
            epsabs=epsabs,                  # Error condition.
            epsrel=epsrel                   # Relative error condition.
        )
        e_sp_results[i] = coeff * res[0]

    return e_sp_results if isinstance(z, np.ndarray) else e_sp_results[0]


def calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C, epsilon_r=1.0, epsabs=1e-8, epsrel=1e-8):
    """
    Calculates the axial rod image electric field E_{I_rod}(z).

    Returns:
    --------
    E_I_rod : float or np.ndarray
        Rod image electric field magnitude [V/m].
    """
    # Note the negative sign in the front coefficient: -1 / (2 * eps_r * eps_0)
    coeff = -1.0 / (2.0 * epsilon_r * EPSILON_0)
    theta_max = theta_B / 2.0

    z_arr = np.atleast_1d(z)
    e_rod_results = np.zeros_like(z_arr, dtype=float)

    for i, z_val in enumerate(z_arr):
        res = dblquad(
            _e_rod_image_integrand,
            0.0, theta_max,
            lambda _: 0.0,
            lambda _: L_cs,
            args=(z_val, R, A, B, C),
            epsabs=epsabs,
            epsrel=epsrel
        )
        e_rod_results[i] = coeff * res[0]

    return e_rod_results if isinstance(z, np.ndarray) else e_rod_results[0]



def _e_plane_image_integrand(r, theta, z, d, R, A, B, C):
    """
    Evaluates the scalar integrand of E_{I_plane} at a single point (r, theta).
    """
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # Axial displacement from the grounded plane image charge to field point z
    # dz_plane = 2d - r*cos(theta) - R - z
    dz_plane = (2.0 * d) - (r * cos_t) - R - z

    # Distance r5 from the plane image charge element to the field point
    r5 = np.sqrt((r * sin_t)**2 + dz_plane**2)

    # Safeguard against division by zero
    if r5 == 0:
        return 0.0

    # Charge density at r
    rho = charge_density(r, A, B, C)

    # Integrand: [rho * r^2 * sin(theta) / r5^3] * dz_plane
    numerator = rho * (r**2) * sin_t * dz_plane
    denominator = r5**3

    return numerator / denominator


def calculate_e_plane_image(z, d, R, L_cs, theta_B, A, B, C, epsilon_r=1.0, epsabs=1e-8, epsrel=1e-8):
    """
    Calculates the axial grounded plane image electric field E_{I_plane}(z).

    Parameters:
    -----------
    z : float or np.ndarray
        Observation point(s) along the symmetry axis [m].
    d : float
        Total gap distance from rod tip to grounded plane [m].
    R : float
        Rod tip radius [m].
    L_cs : float
        Length of space charge region [m].
    theta_B : float
        Total cone boundary angle [rad].
    A, B, C : float
        Parameters for charge density rho(r) = A * (r + C)^B.
    epsilon_r : float
        Relative permittivity of ambient medium (default = 1.0 for air).
    epsabs, epsrel : float
        Absolute and relative error tolerances for adaptive quadrature.
        
    Returns:
    --------
    E_I_plane : float or np.ndarray
        Grounded plane image electric field magnitude [V/m].
    """
    # Front coefficient matches the direct space charge: +1 / (2 * eps_r * eps_0)
    coeff = 1.0 / (2.0 * epsilon_r * EPSILON_0)
    theta_max = theta_B / 2.0

    z_arr = np.atleast_1d(z)
    e_plane_results = np.zeros_like(z_arr, dtype=float)

    for i, z_val in enumerate(z_arr):
        res = dblquad(
            _e_plane_image_integrand,
            0.0, theta_max,
            lambda _: 0.0,
            lambda _: L_cs,
            args=(z_val, d, R, A, B, C),
            epsabs=epsabs,
            epsrel=epsrel
        )
        e_plane_results[i] = coeff * res[0]

    return e_plane_results if isinstance(z, np.ndarray) else e_plane_results[0]


def calculate_total_field(z, d, R, L_cs, theta_B, A, B, C, V_applied, epsilon_r=1.0):
    """
    Calculates total electric field along the gap axis including 
    external geometric field, space charge, rod image, and plane image.
    """

    # TODO: Use the Charge Simulation Method
    # 1. External field approximation (e.g., standard hyperbolic or parallel plate baseline)
    # Depending on your specific formulation, substitute your external field term here:
    E_ext = V_applied / d # Placeholder or your specific rod-plane geometric field function

    # 2. Compute individual space-charge components
    E_sp = calculate_e_sp(z, R, L_cs, theta_B, A, B, C, epsilon_r)
    E_rod_img = calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C, epsilon_r)
    E_plane_img = calculate_e_plane_image(z, d, R, L_cs, theta_B, A, B, C, epsilon_r)

    return E_ext + E_sp + E_rod_img + E_plane_img


