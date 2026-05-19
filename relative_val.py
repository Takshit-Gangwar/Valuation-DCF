import yfinance as yf
import numpy as np


def get_percentiles(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    current_pe = info.get('trailingPE')
    current_pb = info.get('priceToBook')
    current_ev_ebitda = info.get('enterpriseToEbitda')
    current_ps = info.get('priceToSalesTrailing12Months')

    hist = stock.history(period='3y')
    if hist.empty:
        return {}

    fs = stock.financials
    bs = stock.balance_sheet
    if fs is None or fs.empty:
        return {}

    def _find(fs, names):
        for name in names:
            for idx in fs.index:
                if str(idx).lower().strip() == name.lower().strip():
                    return fs.loc[idx]
        return None

    revenue_s = _find(fs, ['Total Revenue'])
    net_income_s = _find(fs, ['Net Income'])
    ebitda_s = _find(fs, ['EBITDA'])
    equity_s = _find(bs, ['Stockholders Equity'])

    if revenue_s is None:
        return {}

    revenue_s = revenue_s.dropna().sort_index()
    net_income_s = net_income_s.dropna().sort_index() if net_income_s is not None else None
    equity_s = equity_s.dropna().sort_index() if equity_s is not None else None

    annual_prices = hist['Close'].resample('YE').last()
    annual_prices = annual_prices[annual_prices.index.year >= annual_prices.index.year[-1] - 3]

    pe_vals = []
    pb_vals = []
    evebitda_vals = []
    ps_vals = []

    shares = info.get('sharesOutstanding')

    for yr in annual_prices.index:
        price = annual_prices[yr]
        yr_num = yr.year

        ni = None
        rev = None
        ebitda = None
        eq = None

        if net_income_s is not None and yr_num in [d.year for d in net_income_s.index]:
            ni = float(net_income_s[net_income_s.index.year == yr_num].iloc[0])
        if equity_s is not None and yr_num in [d.year for d in equity_s.index]:
            eq = float(equity_s[equity_s.index.year == yr_num].iloc[0])
        if revenue_s is not None and yr_num in [d.year for d in revenue_s.index]:
            rev = float(revenue_s[revenue_s.index.year == yr_num].iloc[0])

        if price and shares and ni:
            pe_vals.append(price * shares / abs(ni))
        if price and eq and shares:
            pb_vals.append(price * shares / eq)
        if price and rev and shares:
            ps_vals.append(price * shares / rev)

    def percentile(val, arr):
        if val is None or not arr:
            return None
        return np.sum(np.array(arr) <= val) / len(arr)

    result = {}
    if pe_vals and current_pe:
        result['pe'] = {'current': current_pe, 'low': min(pe_vals), 'high': max(pe_vals), 'pct': percentile(current_pe, pe_vals)}

    if pb_vals and current_pb:
        result['pb'] = {'current': current_pb, 'low': min(pb_vals), 'high': max(pb_vals), 'pct': percentile(current_pb, pb_vals)}

    if ps_vals and current_ps:
        result['ps'] = {'current': current_ps, 'low': min(ps_vals), 'high': max(ps_vals), 'pct': percentile(current_ps, ps_vals)}

    if current_ev_ebitda is not None:
        result['ev_ebitda'] = {'current': current_ev_ebitda, 'low': None, 'high': None, 'pct': None}

    return result
