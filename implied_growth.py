from dcf_model import run_dcf


def implied_growth_rate(data, target_price=None, wacc=None):
    if target_price is None:
        target_price = data.get('price')
    if target_price is None or target_price <= 0:
        return None

    low, high = -0.50, 0.50
    for _ in range(60):
        mid = (low + high) / 2
        d = dict(data)
        r = run_dcf(d, wacc_override=wacc, market_premium=None, growth_override=mid)
        iv = r['intrinsic_value']
        if iv is None or iv <= 0:
            return None
        if iv > target_price:
            high = mid
        else:
            low = mid

    result = (low + high) / 2
    return float(round(result, 4))
