import numpy as np


def estimate_growth_rate(fcf_values):
    pos = [f for f in fcf_values if f > 0]
    if len(pos) >= 3:
        x = np.arange(len(pos))
        log_y = np.log(pos)
        slope = np.polyfit(x, log_y, 1)[0]
        rate = np.exp(slope) - 1
    elif len(pos) >= 2:
        rates = [pos[i] / pos[i - 1] - 1 for i in range(1, len(pos))]
        rate = np.mean(rates)
    else:
        rate = 0.05
    return float(np.clip(rate, -0.50, 0.50))


def project_fcfs(last_fcf, growth_rate, years):
    return [last_fcf * (1 + growth_rate) ** i for i in range(1, years + 1)]


def calc_wacc(beta, tax_rate, debt, market_cap, rf_rate, market_premium=0.055):
    if market_cap and market_cap > 0:
        cost_equity = rf_rate + (beta or 1.0) * market_premium
        cost_debt = (rf_rate + 0.02) * (1 - tax_rate)
        total = market_cap + debt
        wacc = (market_cap / total) * cost_equity + (debt / total) * cost_debt
    else:
        wacc = rf_rate + 0.04
    return wacc


def calc_terminal_value(last_fcf, wacc, terminal_growth_rate):
    if wacc <= terminal_growth_rate:
        terminal_growth_rate = wacc * 0.5
    return last_fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)


def discount_cash_flows(fcfs, wacc):
    pv = 0.0
    for i, fcf in enumerate(fcfs, 1):
        pv += fcf / (1 + wacc) ** i
    return pv


def run_dcf(data, wacc_override=None, market_premium=None, growth_override=None):
    fcfs = data['historical_fcfs']
    fcf_values = [f for _, f in fcfs]

    estimated_growth = estimate_growth_rate(fcf_values)
    growth_rate = growth_override if growth_override is not None else estimated_growth
    n_years = data['projection_years']
    last_fcf = fcf_values[-1]
    projected = project_fcfs(last_fcf, growth_rate, n_years)

    if wacc_override is not None:
        wacc = wacc_override
    else:
        market_cap = data.get('market_cap')
        if market_cap is None and data.get('price') and data.get('shares_outstanding'):
            market_cap = data['price'] * data['shares_outstanding']
        wacc = calc_wacc(
            data['beta'], data['tax_rate'], data['total_debt'],
            market_cap, data['rf_rate'],
            market_premium or 0.055
        )

    terminal_g = data.get('terminal_growth_rate', 0.025)
    tv = calc_terminal_value(projected[-1], wacc, terminal_g)

    pv_fcfs = discount_cash_flows(projected, wacc)
    pv_tv = tv / (1 + wacc) ** n_years
    ev = pv_fcfs + pv_tv

    equity = ev - data['total_debt'] + data['cash']

    if data['shares_outstanding'] and data['shares_outstanding'] > 0:
        intrinsic = equity / data['shares_outstanding']
        upside = intrinsic / data['price'] - 1
    else:
        intrinsic = None
        upside = None

    return {
        'growth_rate': growth_rate,
        'estimated_growth': estimated_growth,
        'wacc': wacc,
        'projected_fcfs': projected,
        'terminal_value': tv,
        'pv_fcfs': pv_fcfs,
        'pv_tv': pv_tv,
        'enterprise_value': ev,
        'equity_value': equity,
        'intrinsic_value': intrinsic,
        'current_price': data['price'],
        'upside': upside,
    }
