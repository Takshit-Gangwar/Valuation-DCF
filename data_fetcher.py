import yfinance as yf


def search_tickers(query):
    try:
        s = yf.Search(query)
        raw = []
        for q in (s.quotes or []):
            symbol = q.get('symbol', '')
            name = q.get('shortname') or q.get('longname') or ''
            exch = q.get('exchange', '')
            typ = q.get('typeDisp', '')
            if not symbol or not name:
                continue
            if symbol.startswith('0P'):
                continue
            if typ and typ.lower() != 'equity':
                continue
            if exch in ('NSI', 'BSE') or symbol.endswith('.NS') or symbol.endswith('.BO'):
                raw.append({'symbol': symbol, 'name': name, 'exchange': exch})

        # Prefer NSE over BSE when the same company appears on both
        nse_symbols = {r['symbol'].replace('.NS', '') for r in raw if r['symbol'].endswith('.NS')}
        results = [r for r in raw if not (r['symbol'].endswith('.BO') and r['symbol'].replace('.BO', '') in nse_symbols)]

        return results[:12]
    except Exception:
        return []


def get_risk_free_rate():
    return 0.07


def get_financials(ticker):
    stock = yf.Ticker(ticker)
    cf = stock.cashflow

    if cf is None or cf.empty:
        raise ValueError(f"No cash flow data found for {ticker}")

    ocf_key = capex_key = None
    for idx in cf.index:
        s = str(idx).lower()
        if ocf_key is None and ('operating' in s and 'cash' in s):
            ocf_key = idx
        if capex_key is None and ('capital' in s and 'expenditure' in s):
            capex_key = idx

    if ocf_key is None or capex_key is None:
        raise ValueError(
            f"Could not locate Operating Cash Flow / Capital Expenditure for {ticker}. "
            f"Available fields: {list(cf.index)}"
        )

    ocf = cf.loc[ocf_key].dropna()
    capex = cf.loc[capex_key].dropna()

    common = sorted(ocf.index.intersection(capex.index))
    if len(common) < 3:
        raise ValueError(f"Need at least 3 years of FCF data, got {len(common)}")

    fcfs = []
    for dt in common:
        fcf = float(ocf[dt]) + float(capex[dt])
        fcfs.append((dt.to_pydatetime(), fcf))

    return fcfs


def get_market_data(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    price = info.get('currentPrice') or info.get('regularMarketPrice')
    if price is None:
        hist = stock.history(period="1d")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])

    if price is None:
        raise ValueError(f"Could not get current price for {ticker}")

    return {
        'price': price,
        'shares_outstanding': info.get('sharesOutstanding'),
        'beta': info.get('beta'),
        'market_cap': info.get('marketCap'),
    }


def get_balance_sheet(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    debt = info.get('totalDebt')
    cash = info.get('totalCash')

    if debt is None or cash is None:
        bs = stock.balance_sheet
        if bs is not None and not bs.empty:
            for idx in bs.index:
                s = str(idx).lower()
                if debt is None and 'total debt' in s:
                    debt = float(bs.loc[idx].dropna().iloc[0])
                if cash is None and ('cash and cash equivalents' in s or s == 'cash'):
                    cash = float(bs.loc[idx].dropna().iloc[0])

    return {
        'total_debt': debt or 0,
        'cash': cash or 0,
    }


def get_tax_rate(ticker):
    return 0.25
