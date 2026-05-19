import numpy as np
from dcf_model import run_dcf


def run_monte_carlo(data, iterations=10000, growth_vol=0.05, wacc_vol=0.01):
    growth = data.get('_estimated_growth', 0.05)
    wacc = data.get('_wacc', 0.10)

    np.random.seed(42)
    growth_samples = np.random.normal(growth, growth_vol, iterations)
    wacc_samples = np.random.normal(wacc, wacc_vol, iterations)

    growth_samples = np.clip(growth_samples, -0.50, 0.50)
    wacc_samples = np.clip(wacc_samples, 0.03, 0.25)

    results = []
    for i in range(iterations):
        d = dict(data)
        r = run_dcf(d, wacc_override=float(wacc_samples[i]),
                    market_premium=None,
                    growth_override=float(growth_samples[i]))
        iv = r['intrinsic_value']
        if iv is not None and iv > 0:
            results.append(iv)

    return results
