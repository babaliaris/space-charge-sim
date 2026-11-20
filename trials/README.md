# Trials (current case only)

Current case: `rate_lag/`

Model: B = 1.5, C = 0.035 cm (the paper's values, inputs), theta_B = 93.39 deg, charge of every
burst from Gauss's law over its head minus the older charge inside the new cone, length = largest
root of the head condition, rigid drift, and a RATE-DEPENDENT TIME LAG: every burst happens when the tip field reaches
E0 + k (dE_tip/dt)^n, where dE_tip/dt is the rate of rise when the tip field first reaches E0 = V0 e_ex(0).
For the first burst this is V1 = V0 + k (dV/dt)^n with V0 = 8.53 kV (40 cm gap; same field law in the
80 cm gap), k = 7.68 kV/(kV/us)^n, n = 0.316, fitted to the paper's measured first-streamer voltages
(Fig. 6, 40 cm); everything else is a prediction. Independent check: the Fig. 3 impulse (320 kV,
130 us, 80 cm) gives V1 = 26.4 kV (paper 27.5 kV). Regenerate with:

    python trials/make_trials.py --name rate_lag --B 1.5 --C 0.035 --theta 93.39 --subtract --rate-lag

Error: NRMSE = RMS(this work - paper) / RMS(paper) x 100 %, against the paper's measured curves
(Fig. 4: against the digitized E_sp before/after the drift). The numbers are in the legends of the
charts (`png/`, `plots/`), in the "Comparison" sheet, point by point in the "Values" sheet, and the
fit of V0 and tau in the "Rate-lag fit" sheet of `fig678_rate_lag.xlsx`; `summary.txt` lists them.
