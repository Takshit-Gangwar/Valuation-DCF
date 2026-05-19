from dcf_model import run_dcf


def run_scenarios(data, result):
    base_growth = result.get('estimated_growth', result.get('growth_rate', 0.05))
    base_wacc = result['wacc']

    scenarios = {}

    params = {
        'bull': {'growth': base_growth * 1.5, 'wacc': base_wacc * 0.9, 'tg': data.get('terminal_growth_rate', 0.04) * 1.2},
        'base': {'growth': base_growth, 'wacc': base_wacc, 'tg': data.get('terminal_growth_rate', 0.04)},
        'bear': {'growth': max(base_growth * 0.5, -0.50), 'wacc': base_wacc * 1.1, 'tg': data.get('terminal_growth_rate', 0.04) * 0.8},
    }

    for name, p in params.items():
        d = dict(data)
        d['terminal_growth_rate'] = p['tg']
        r = run_dcf(d, wacc_override=p['wacc'], market_premium=None, growth_override=p['growth'])
        scenarios[name] = {
            'intrinsic': r['intrinsic_value'],
            'upside': r['upside'],
            'growth': p['growth'],
            'wacc': p['wacc'],
            'terminal_g': p['tg'],
            'ev': r['enterprise_value'],
            'equity': r['equity_value'],
        }

    return scenarios
