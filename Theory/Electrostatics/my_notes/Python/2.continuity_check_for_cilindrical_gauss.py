import numpy as np
import matplotlib.pyplot as plt

# Σταθερές
Ps = 1.0                 # επιφανειακή πυκνότητα
eps_out = 2.0            # διηλεκτρική σταθερά εξωτερικού μέσου
a = 1.0                  # ακτίνα κυλίνδρου
P_inf = 5.0              # απόσταση αναφοράς για το δυναμικό

# Περιοχή ακτίνων
rho_inside = np.linspace(0, a, 100, endpoint=False)
rho_outside = np.linspace(a, 3*a, 200)

# Θεωρητικά ύψη
height_D = Ps
height_E = Ps / eps_out
height_phi = (a * Ps / eps_out) * np.log(P_inf / a)

# D(ρ)
D_outside = Ps * a / rho_outside

# E(ρ)
E_outside = (Ps * a / eps_out) / rho_outside

# φ(ρ)
phi_inside = np.full_like(rho_inside, height_phi)
phi_outside = (a * Ps / eps_out) * np.log(P_inf / rho_outside)

# Plot
fig, ax = plt.subplots(figsize=(8, 5))

# Καμπύλες
ax.plot(rho_outside, D_outside, 'b', lw=2, label='$D(\\rho)$')
ax.plot(rho_outside, E_outside, 'g', lw=2, label='$E(\\rho)$')
ax.plot(rho_inside, phi_inside, 'r', lw=2, label='$\\phi(\\rho)$')
ax.plot(rho_outside, phi_outside, 'r', lw=2)

# Κάθετη γραμμή στο ρ = 0 (αρχή του φ)
ax.axvline(x=0, color='k', linestyle='--', alpha=0.7)
ax.text(0, ax.get_ylim()[0] - 0.05*(ax.get_ylim()[1] - ax.get_ylim()[0]),
        r'$\rho = 0$', ha='center', va='top', fontsize=12)

# Κάθετη γραμμή στο ρ = a
ax.axvline(x=a, color='k', linestyle='--', alpha=0.7)
ax.text(a, ax.get_ylim()[0] - 0.05*(ax.get_ylim()[1] - ax.get_ylim()[0]),
        r'$\rho = a$', ha='center', va='top', fontsize=12)

# Labels στα αριστερά
ax.text(-0.2, height_D, r'$P_s$', color='b', fontsize=12, va='center', ha='right')
ax.text(-0.2, height_E, r'$\frac{P_s}{\varepsilon}$', color='g', fontsize=12, va='center', ha='right')
ax.text(-0.2, height_phi, r'$\frac{aP_s}{\varepsilon} \ln\left|\frac{P_{\infty}}{a}\right|$', 
        color='r', fontsize=12, va='center', ha='right')

# Στυλ
ax.set_xlabel(r'$\rho$')
ax.set_ylabel('Μεγέθη')
ax.legend()

# Απόκρυψη αριθμών αξόνων
ax.set_xticks([])
ax.set_yticks([])

ax.set_xlim(-0.5, 3*a)
ax.grid(True, linestyle='--', alpha=0.3)

plt.tight_layout()
plt.show()
