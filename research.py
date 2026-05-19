import yfinance as yf
import numpy as np


def _get_last(fs, names, n=5):
    if fs is None or fs.empty:
        return {}
    for name in names:
        for idx in fs.index:
            if str(idx).lower().strip() == name.lower().strip():
                vals = fs.loc[idx].dropna().sort_index()
                return {dt.year: float(vals[dt]) for dt in vals.index[-n:]}
    return {}


def _calc_cagr(vals):
    vals = [v for v in vals if v and v > 0]
    if len(vals) < 2:
        return None
    return (vals[-1] / vals[0]) ** (1.0 / (len(vals) - 1)) - 1


def _calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def generate_report(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    fs = stock.financials
    bs = stock.balance_sheet

    # ── Company Profile ──
    profile = {
        'name': info.get('longName') or info.get('shortName'),
        'sector': info.get('sector'),
        'industry': info.get('industry'),
        'employees': info.get('fullTimeEmployees'),
        'country': info.get('country'),
        'website': info.get('website'),
        'description': info.get('longBusinessSummary'),
    }

    # ── Profitability ──
    revenues = _get_last(fs, ['Total Revenue', 'Revenue'], 5)
    net_incomes = _get_last(fs, ['Net Income', 'Net Income Common Stockholders'], 5)
    gross_profits = _get_last(fs, ['Gross Profit'], 5)
    op_incomes = _get_last(fs, ['Operating Income'], 5)

    margins = {}
    for yr in revenues:
        r = revenues.get(yr)
        gp = gross_profits.get(yr)
        oi = op_incomes.get(yr)
        ni = net_incomes.get(yr)
        margins[yr] = {
            'gross': gp / r if r and gp else None,
            'operating': oi / r if r and oi else None,
            'net': ni / r if r and ni else None,
        }

    # ── Financial Health ──
    equity = _get_last(bs, ['Stockholders Equity', 'Total Equity Gross Minority Interest'], 1)
    total_debt = _get_last(bs, ['Total Debt'], 1)
    total_assets = _get_last(bs, ['Total Assets'], 1)
    current_assets = _get_last(bs, ['Current Assets'], 1)
    current_liab = _get_last(bs, ['Current Liabilities'], 1)
    ebit = _get_last(fs, ['EBIT'], 1)
    interest = _get_last(fs, ['Interest Expense', 'Interest Expense Net'], 1)

    eq_val = next(iter(equity.values())) if equity else 0
    debt_val = next(iter(total_debt.values())) if total_debt else 0
    ta_val = next(iter(total_assets.values())) if total_assets else 0
    ca_val = next(iter(current_assets.values())) if current_assets else 0
    cl_val = next(iter(current_liab.values())) if current_liab else 0
    ebit_val = next(iter(ebit.values())) if ebit else 0
    int_val = next(iter(interest.values())) if interest else -1

    ni_vals = list(net_incomes.values())
    latest_ni = ni_vals[-1] if ni_vals else 0

    health = {
        'roe': latest_ni / eq_val if eq_val else None,
        'roa': latest_ni / ta_val if ta_val else None,
        'debt_equity': debt_val / eq_val if eq_val else None,
        'current_ratio': ca_val / cl_val if cl_val else None,
        'interest_coverage': ebit_val / abs(int_val) if int_val and int_val != 0 and ebit_val else None,
    }

    # ── Growth Rates ──
    growth = {
        'revenue_cagr_3y': _calc_cagr(list(revenues.values())[-4:]),
        'revenue_cagr_5y': _calc_cagr(list(revenues.values())),
        'earnings_cagr_3y': _calc_cagr(list(net_incomes.values())[-4:]),
        'earnings_cagr_5y': _calc_cagr(list(net_incomes.values())),
    }

    # ── Valuation Metrics ──
    valuation = {
        'pe_trailing': info.get('trailingPE'),
        'pe_forward': info.get('forwardPE'),
        'pb': info.get('priceToBook'),
        'ps': info.get('priceToSalesTrailing12Months'),
        'ev_ebitda': info.get('enterpriseToEbitda'),
        'dividend_yield': info.get('dividendYield'),
        'payout_ratio': info.get('payoutRatio'),
        'market_cap': info.get('marketCap'),
    }

    # ── Price Momentum ──
    hist = stock.history(period="1y")
    momentum = {'high_52w': None, 'low_52w': None, 'return_1m': None,
                'return_3m': None, 'return_6m': None, 'return_12m': None,
                'rsi': None, 'beta': None}
    if not hist.empty:
        closes = hist['Close']
        momentum['high_52w'] = float(closes.max())
        momentum['low_52w'] = float(closes.min())
        momentum['return_12m'] = float((closes.iloc[-1] / closes.iloc[0]) - 1) if len(closes) > 0 else None
        if len(closes) >= 130:
            momentum['return_6m'] = float((closes.iloc[-1] / closes.iloc[-130]) - 1)
        if len(closes) >= 65:
            momentum['return_3m'] = float((closes.iloc[-1] / closes.iloc[-65]) - 1)
        if len(closes) >= 22:
            momentum['return_1m'] = float((closes.iloc[-1] / closes.iloc[-22]) - 1)
        momentum['rsi'] = float(round(_calc_rsi(closes.values), 1)) if _calc_rsi(closes.values) is not None else None

    beta = info.get('beta')
    momentum['beta'] = beta

    # ── Sector context (no auto peer list, just note sector) ──
    sector_name = info.get('sector', '')

    return {
        'profile': profile,
        'revenues': revenues,
        'net_incomes': net_incomes,
        'margins': margins,
        'health': health,
        'growth': growth,
        'valuation': valuation,
        'momentum': momentum,
        'sector': sector_name,
    }
