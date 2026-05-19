def analyze(result, data):
    intrinsic = result.get('intrinsic_value')
    price = result.get('current_price')
    upside = result.get('upside')
    growth = result.get('growth_rate')
    wacc = result.get('wacc')
    terminal_g = data.get('terminal_growth_rate', 0.04)
    beta = data.get('beta')
    total_debt = data.get('total_debt', 0)
    shares = data.get('shares_outstanding')
    market_cap = data.get('market_cap')
    if not market_cap and price and shares:
        market_cap = price * shares

    reasons = []

    # ── Model validity ──
    if intrinsic is None:
        return {
            'action': 'INCONCLUSIVE',
            'confidence': 'LOW',
            'summary': 'Could not calculate intrinsic value (missing shares outstanding)',
            'reasons': ['No reliable intrinsic value to compare against'],
        }

    if wacc and terminal_g and wacc <= terminal_g:
        return {
            'action': 'INCONCLUSIVE',
            'confidence': 'LOW',
            'summary': 'WACC is less than terminal growth rate \u2014 model unreliable',
            'reasons': [f'WACC ({wacc:.1%}) \u2264 Terminal Growth ({terminal_g:.1%})'],
        }

    # ── Base signal from upside ──
    if upside >= 0.15:
        action = 'BUY'
        confidence = 'HIGH'
        reasons.append(f'Upside of {upside:.1%} exceeds 15% margin of safety')
    elif upside <= -0.15:
        action = 'SHORT'
        confidence = 'MEDIUM'
        reasons.append(f'Downside of {abs(upside):.1%} exceeds -15% threshold')
    else:
        reasons.append(f'Upside of {upside:.1%} is within \u00b115% \u2014 no clear edge')
        return {
            'action': "DON'T BUY",
            'confidence': 'MEDIUM',
            'summary': f'Stock is fairly valued (within \u00b115% of intrinsic value)',
            'reasons': reasons,
        }

    # ── Risk adjustments ──
    if action == 'BUY':
        if growth is not None and growth <= 0:
            action = "DON'T BUY"
            confidence = 'LOW'
            reasons.append(f'FCF declining at {growth:.1%} \u2014 not buying a shrinking business')
        elif market_cap and market_cap > 0:
            debt_ratio = total_debt / market_cap
            if debt_ratio > 0.5:
                action = "DON'T BUY"
                confidence = 'LOW'
                reasons.append(f'Debt/Equity of {debt_ratio:.0%} exceeds 50% \u2014 too risky')
        if beta is not None and beta > 1.5 and action == 'BUY':
            confidence = 'LOW'
            reasons.append(f'High beta of {beta:.2f} makes this a risky buy')

    elif action == 'SHORT':
        if growth is not None and growth > 0:
            action = "DON'T BUY"
            confidence = 'LOW'
            reasons.append(f'FCF growing at {growth:.1%} \u2014 shorting a growing company is risky')
        if beta is not None and beta > 1.5 and action == 'SHORT':
            confidence = 'LOW'
            reasons.append(f'High beta of {beta:.2f} makes a short position volatile')

    # ── Summary ──
    if action == 'BUY':
        growth_note = f' with {growth:.1%} FCF growth' if growth and growth > 0 else ''
        summary = f'Stock is undervalued \u2014 {upside:.0%} upside{growth_note}'
    elif action == 'SHORT':
        decline_note = f' with declining FCFs' if growth and growth < 0 else ''
        summary = f'Stock is overvalued \u2014 {abs(upside):.0%} downside{decline_note}'
    else:
        summary = 'No actionable signal \u2014 conflicting risk factors'

    return {
        'action': action,
        'confidence': confidence,
        'summary': summary,
        'reasons': reasons,
    }
