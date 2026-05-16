"""Clarke / Park / inverse transforms.

Amplitude-invariant convention. Must stay sign-consistent with
`Alva.SlotlessPMSM_abc` in modelica/Alva.mo (which uses the same form).
"""

from __future__ import annotations

import math

SQRT3 = math.sqrt(3.0)


def clarke(a: float, b: float, c: float) -> tuple[float, float]:
    """Amplitude-invariant 3 -> 2 Clarke transform.

    alpha = (2/3)*(a - 0.5*b - 0.5*c)
    beta  = (1/sqrt(3))*(b - c)
    """
    alpha = (2.0 / 3.0) * (a - 0.5 * b - 0.5 * c)
    beta = (b - c) / SQRT3
    return alpha, beta


def inv_clarke(alpha: float, beta: float) -> tuple[float, float, float]:
    """Inverse Clarke: alpha-beta -> a/b/c (balanced 3-phase, a + b + c = 0).

    a =  alpha
    b = -0.5*alpha + (sqrt(3)/2)*beta
    c = -0.5*alpha - (sqrt(3)/2)*beta
    """
    a = alpha
    b = -0.5 * alpha + (SQRT3 / 2.0) * beta
    c = -0.5 * alpha - (SQRT3 / 2.0) * beta
    return a, b, c


def park(alpha: float, beta: float, theta_e: float) -> tuple[float, float]:
    """Stationary alpha-beta -> rotating d-q using electrical angle theta_e.

    d =  cos(theta_e)*alpha + sin(theta_e)*beta
    q = -sin(theta_e)*alpha + cos(theta_e)*beta
    """
    cos_t = math.cos(theta_e)
    sin_t = math.sin(theta_e)
    d = alpha * cos_t + beta * sin_t
    q = -alpha * sin_t + beta * cos_t
    return d, q


def inv_park(d: float, q: float, theta_e: float) -> tuple[float, float]:
    """Rotating d-q -> stationary alpha-beta.

    alpha = cos(theta_e)*d - sin(theta_e)*q
    beta  = sin(theta_e)*d + cos(theta_e)*q
    """
    cos_t = math.cos(theta_e)
    sin_t = math.sin(theta_e)
    alpha = d * cos_t - q * sin_t
    beta = d * sin_t + q * cos_t
    return alpha, beta


def abc_to_dq(a: float, b: float, c: float, theta_e: float) -> tuple[float, float]:
    """Composed Clarke + Park: i_abc + theta_e -> i_dq."""
    alpha, beta = clarke(a, b, c)
    return park(alpha, beta, theta_e)


def dq_to_abc(d: float, q: float, theta_e: float) -> tuple[float, float, float]:
    """Composed InvPark + InvClarke: v_dq + theta_e -> v_abc."""
    alpha, beta = inv_park(d, q, theta_e)
    return inv_clarke(alpha, beta)


if __name__ == "__main__":
    # Round-trip sanity:
    #   - Clarke -> InvClarke is identity on balanced triples (a + b + c = 0).
    #   - Park   -> InvPark   is identity on any (d, q).
    import random

    random.seed(0)
    for _ in range(100):
        a = random.uniform(-10, 10)
        b = random.uniform(-10, 10)
        c = -(a + b)
        alpha, beta = clarke(a, b, c)
        a2, b2, c2 = inv_clarke(alpha, beta)
        assert abs(a - a2) < 1e-9, (a, a2)
        assert abs(b - b2) < 1e-9, (b, b2)
        assert abs(c - c2) < 1e-9, (c, c2)

        theta = random.uniform(-10, 10)
        d, q = park(alpha, beta, theta)
        alpha2, beta2 = inv_park(d, q, theta)
        assert abs(alpha - alpha2) < 1e-9, (alpha, alpha2)
        assert abs(beta - beta2) < 1e-9, (beta, beta2)

        # Composed round-trip: i_abc -> dq -> i_abc.
        d2, q2 = abc_to_dq(a, b, c, theta)
        a3, b3, c3 = dq_to_abc(d2, q2, theta)
        assert abs(a - a3) < 1e-9, (a, a3)
        assert abs(b - b3) < 1e-9, (b, b3)
        assert abs(c - c3) < 1e-9, (c, c3)

    print("transform.py: Clarke/Park round-trips OK")
