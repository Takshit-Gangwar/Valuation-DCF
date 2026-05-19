from dcf_model import run_dcf


def build_sensitivity(data, wacc_steps=7, tg_steps=5):
    base_wacc = data.get('_wacc', 0.10)
    base_tg = data.get('terminal_growth_rate', 0.04)

    wacc_range = [base_wacc - 0.03 + i * 0.01 for i in range(wacc_steps)]
    tg_range = [max(0.01, base_tg - 0.02 + i * 0.01) for i in range(tg_steps)]

    table = []
    for w in wacc_range:
        row = []
        for tg in tg_range:
            d = dict(data)
            d['terminal_growth_rate'] = tg
            r = run_dcf(d, wacc_override=w, market_premium=None)
            row.append(r['intrinsic_value'])
        table.append(row)

    return {
        'wacc_range': wacc_range,
        'tg_range': tg_range,
        'values': table,
        'current_price': data.get('price'),
    }
