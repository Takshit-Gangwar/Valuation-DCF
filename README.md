# DCF Stock Valuation Model

A discounted cash flow (DCF) stock valuation application for Indian markets (NSE/BSE), available as both a **Tkinter desktop app** and a **Streamlit web app**.

## Features

- **DCF Valuation** — Calculate intrinsic value per share using discounted cash flow analysis with log-linear regression growth estimation
- **Recommendation Engine** — BUY/SHORT/DON'T BUY signals with ±15% margin of safety, incorporating debt/equity, FCF growth trend, and beta
- **Scenario Analysis** — Bull/Base/Bear cases with varying growth, WACC, and terminal growth assumptions
- **Implied Growth** — Reverse-DCF binary search solver for the growth rate the market is pricing in
- **Sensitivity Matrix** — WACC × Terminal Growth rate grid with color-coded undervalued/overvalued cells
- **Cash Flow Chart** — Bar chart of historical + projected FCF with present value overlay
- **Relative Valuation** — 3-year historical percentile ranking for P/E, P/B, P/S, EV/EBITDA
- **Monte Carlo Simulation** — 1,000–50,000 randomized DCF iterations with histogram and probability statistics
- **Fundamental Research** — Comprehensive report including profitability trends, financial health ratios, growth CAGRs, valuation multiples, price momentum, and RSI
- **Watchlist** — Track multiple tickers with one-click DCF refresh
- **CSV Export** — Export valuation reports to CSV

### Indian Market Specifics

- Equities only — no mutual fund scheme codes (0P prefix filtered out)
- BSE duplicates removed when NSE ticker exists
- Risk-free rate: 7% (India), Equity risk premium: 7%
- Tax rate: 25% flat
- Terminal growth default: 4.0%
- Currency: Rs, formatted in crores (Cr) and lakhs (L)
- Ticker auto-appends `.NS` (NSE) if no exchange suffix given

## Quick Start

### Desktop App (Tkinter)

```bash
pip install -r requirements.txt
python app.py
```

### Web App (Streamlit)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Usage

1. Enter a ticker symbol (e.g. `TCS`, `RELIANCE`, `HDFCBANK`) — `.NS` is appended automatically for NSE
2. Click **Calculate** to run the DCF valuation
3. Switch between tabs to explore different analyses:
   - **DCF** — Core valuation results, recommendation, and cash flow projections
   - **Scenarios** — Bull/Base/Bear case comparison
   - **Implied G** — Market-implied growth rate vs historical growth
   - **Sensitivity** — WACC × Terminal Growth rate matrix
   - **Charts** — FCF bar chart with PV overlay
   - **Rel Val** — Percentile ranking vs 3-year history
   - **Monte Carlo** — Probabilistic simulation
   - **Watchlist** — Portfolio tracking
   - **Export** — CSV download
4. Click **Research** to view the fundamental research report

## Project Structure

| File | Purpose |
|------|---------|
| `app.py` | Tkinter desktop application (9-tab notebook) |
| `streamlit_app.py` | Streamlit web application |
| `data_fetcher.py` | yfinance data layer (financials, market data, balance sheet, tax rate, search) |
| `dcf_model.py` | DCF engine (growth estimation, WACC via CAPM, terminal value, discounting) |
| `recommendation.py` | BUY/SHORT/DON'T BUY decision engine |
| `research.py` | Fundamental research report generator |
| `scenarios.py` | Bull/Base/Bear scenario analysis |
| `implied_growth.py` | Reverse-DCF market-implied growth solver |
| `sensitivity.py` | WACC × terminal growth sensitivity matrix |
| `monte_carlo.py` | Randomized DCF simulation |
| `relative_val.py` | Historical percentile ranking |
| `portfolio.py` | JSON-backed watchlist manager |
| `visualization.py` | Matplotlib FCF bar chart (Tkinter) |
| `research_ui.py` | Tkinter research report UI widgets |
| `export.py` | CSV export |
| `requirements.txt` | Python dependencies |

## Dependencies

- `yfinance` — Yahoo Finance data
- `numpy` — Numerical computation
- `matplotlib` — Charts and visualization
- `streamlit` — Web app framework

## Notes

- The Tkinter app (`app.py`) is the original desktop version. The Streamlit app (`streamlit_app.py`) provides the same functionality as a web interface.
- Both apps share the same underlying modules (`data_fetcher.py`, `dcf_model.py`, etc.) — no code is duplicated.
- Internet connection is required for yfinance data fetching.
- Data is cached per session to avoid redundant API calls.
