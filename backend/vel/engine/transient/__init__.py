"""Time-domain (transient) models, next to the steady-state phasor MNA in vel.engine.

Each model is a small ODE system integrated with SciPy's stiff solvers. Every transient must
settle on the operating point the steady-state solver gives for the same machine — the tests
check that, which ties the two engines together and catches sign/convention errors.
"""
