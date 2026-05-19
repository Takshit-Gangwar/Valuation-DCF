import streamlit as st
import pandas as pd
import numpy as np
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    get_financials, get_market_data, get_balance_sheet,
    get_tax_rate, get_risk_free_rate, search_tickers
)
from dcf_model import run_dcf
from recommendation import analyze
from research import generate_report
from scenarios import run_scenarios
from implied_growth import implied_growth_rate
from sensitivity import build_sensitivity
from export import export_csv
from monte_carlo import run_monte_carlo
from relative_val import get_percentiles

st.set_page_config(page_title="DCF Stock Valuation \u2014 India", layout="wide")

# ── Formatting helpers ──

def fmt_currency(value, sym="Rs"):
    if value is None:
        return "--"
    s = sym + " " if len(sym) > 1 else sym
    if abs(value) >= 1e7:
        return f"{s}{value / 1e7:,.2f} Cr"
    if abs(value) >= 1e5:
        return f"{s}{value / 1e5:,.2f} L"
    return f"{s}{value:,.2f}"


def fmt_pct(value):
    if value is None:
        return "--"
    return f"{value:.1%}"


# ── Matplotlib figure builder (non-Tkinter version) ──

def build_fcf_figure(hist_fcfs, projected_fcfs, wacc, currency_sym="Rs"):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    import matplotlib.ticker as mticker

    fig = Figure(figsize=(7, 3.5), dpi=100)
    ax = fig.add_subplot(111)

    years_h = [dt.year for dt, _ in hist_fcfs]
    vals_h = [f for _, f in hist_fcfs]

    last_yr = years_h[-1]
    years_p = [last_yr + i for i in range(1, len(projected_fcfs) + 1)]

    ax.bar(years_h, [v / 1e7 for v in vals_h],
           color="#4a8bc2", alpha=0.75, label="Historical FCF", width=0.6)
    ax.bar(years_p, [v / 1e7 for v in projected_fcfs],
           color="#2d7d46", alpha=0.75, label="Projected FCF", width=0.6)

    pv = [projected_fcfs[i] / (1 + wacc) ** (i + 1) for i in range(len(projected_fcfs))]
    ax.plot(years_p, [v / 1e7 for v in pv], "r--", linewidth=1.5,
            label="PV of Projected", marker="o", markersize=3)

    ax.axhline(y=0, color="gray", linewidth=0.5)
    ax.set_ylabel("Value (Cr)", fontsize=9)
    ax.set_title("Free Cash Flow Projection", fontsize=10, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    fig.tight_layout()
    return fig


# ── Session state ──

for key in ("last_result", "last_data", "last_ticker", "fetched_data",
            "mc_results", "wl_tickers", "research_report"):
    if key not in st.session_state:
        if key in ("fetched_data", "wl_tickers"):
            st.session_state[key] = {}
        else:
            st.session_state[key] = None

if "wl_tickers" not in st.session_state or st.session_state.wl_tickers is None:
    st.session_state.wl_tickers = []

# ── Top bar ──

st.markdown("## DCF Stock Valuation Model")
tcol1, tcol2, tcol3, tcol4 = st.columns([1.5, 1, 1, 4])
with tcol1:
    ticker_input = st.text_input("Ticker", placeholder="e.g. TCS", label_visibility="collapsed")
with tcol2:
    calc_clicked = st.button("Calculate", type="primary", use_container_width=True)
with tcol3:
    show_research = st.button("Research", use_container_width=True, disabled=not st.session_state.last_ticker)
with tcol4:
    if st.session_state.last_ticker:
        st.markdown(f"**{st.session_state.last_ticker}**  \u2014  Last calculated")

# Ticker resolution
ticker = None
if calc_clicked and ticker_input:
    raw = ticker_input.strip().upper()
    if "." not in raw:
        raw = raw + ".NS"
    ticker = raw

# ── Data fetching + DCF calculation ──

def run_calculation(ticker_symbol):
    try:
        fcfs = get_financials(ticker_symbol)
        mkt = get_market_data(ticker_symbol)
        bs = get_balance_sheet(ticker_symbol)
        tax_rate = get_tax_rate(ticker_symbol)
        rf_rate = get_risk_free_rate()
        data = {
            "historical_fcfs": fcfs,
            "price": mkt["price"],
            "shares_outstanding": mkt["shares_outstanding"],
            "beta": mkt["beta"],
            "market_cap": mkt["market_cap"],
            "total_debt": bs["total_debt"],
            "cash": bs["cash"],
            "tax_rate": tax_rate,
            "rf_rate": rf_rate,
            "projection_years": 5,
            "terminal_growth_rate": 0.04,
        }
        result = run_dcf(data, market_premium=0.07)
        return result, data
    except Exception as e:
        st.error(str(e))
        return None, None

if ticker:
    with st.spinner(f"Fetching data for {ticker} ..."):
        result, data = run_calculation(ticker)
    if result:
        st.session_state.last_result = result
        st.session_state.last_data = data
        st.session_state.last_ticker = ticker
        st.session_state.fetched_data[ticker] = data
        st.rerun()

# ── Tab content helpers ──

def _build_intrinsic_table(result, data):
    """Return DataFrame of intrinsic value breakdown."""
    return pd.DataFrame({
        "Metric": ["Intrinsic Value / Share", "Current Price", "Upside / Downside",
                    "Estimated Growth Rate", "WACC (Discount Rate)",
                    "Terminal Value", "Enterprise Value", "Equity Value"],
        "Value": [
            fmt_currency(result["intrinsic_value"]),
            fmt_currency(result["current_price"]),
            f"{result['upside']:+.1%}" if result.get("upside") is not None else "--",
            fmt_pct(result["growth_rate"]),
            fmt_pct(result["wacc"]),
            fmt_currency(result["terminal_value"]),
            fmt_currency(result["enterprise_value"]),
            fmt_currency(result["equity_value"]),
        ]
    })


def _fcf_table(result, fcfs):
    """Return DataFrame of historical + projected FCFs."""
    rows = []
    for dt, fcf in fcfs:
        rows.append({"Year": str(dt.year), "Historical FCF": fmt_currency(fcf), "Projected FCF": ""})
    last_yr = fcfs[-1][0].year
    for i, fcf in enumerate(result["projected_fcfs"], 1):
        rows.append({"Year": str(last_yr + i), "Historical FCF": "", "Projected FCF": fmt_currency(fcf)})
    return pd.DataFrame(rows)


def _rec_display(result, data):
    """Return recommendation dict with action/confidence/summary/reasons."""
    return analyze(result, data)


# ── Tabs ──

tabs = st.tabs([
    "DCF", "Scenarios", "Implied G", "Sensitivity",
    "Charts", "Rel Val", "Monte Carlo", "Watchlist", "Export"
])

# ──────────────── DCF TAB ────────────────

with tabs[0]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Enter a ticker and click **Calculate** to begin.")
    else:
        with st.expander("Settings", expanded=False):
            scol1, scol2, scol3 = st.columns(3)
            with scol1:
                proj_years = st.number_input("Projection Years", min_value=3, max_value=20, value=5, step=1)
            with scol2:
                wacc_override = st.text_input("Discount Rate (WACC %)", value="Auto")
            with scol3:
                term_g = st.number_input("Terminal Growth %", min_value=0.0, max_value=10.0, value=4.0, step=0.5) / 100

            if st.button("Recalculate", use_container_width=True):
                data["projection_years"] = proj_years
                data["terminal_growth_rate"] = term_g
                override = None
                if wacc_override.strip().lower() != "auto":
                    try:
                        override = float(wacc_override) / 100
                    except ValueError:
                        pass
                with st.spinner("Recalculating ..."):
                    new_result = run_dcf(data, override, market_premium=0.07)
                st.session_state.last_result = new_result
                st.rerun()

        # Results
        rcol1, rcol2 = st.columns([1.2, 2])

        with rcol1:
            rec = _rec_display(result, data)
            action = rec["action"]
            if action == "BUY":
                st.success(f"**{action}** \u2014 {rec['confidence']} CONFIDENCE")
            elif action == "SHORT":
                st.error(f"**{action}** \u2014 {rec['confidence']} CONFIDENCE")
            else:
                st.warning(f"**{action}** \u2014 {rec['confidence']} CONFIDENCE")
            st.caption(rec["summary"])
            for r in rec["reasons"]:
                st.markdown(f"- {r}")

            st.divider()

            df_vals = _build_intrinsic_table(result, data)
            for _, row in df_vals.iterrows():
                m = row["Metric"]
                v = row["Value"]
                if m in ("Intrinsic Value / Share", "Current Price", "Upside / Downside"):
                    st.metric(m, v)
                else:
                    st.markdown(f"**{m}:** {v}")

        with rcol2:
            st.subheader("Cash Flow Projections")
            df_fcf = _fcf_table(result, data["historical_fcfs"])
            st.dataframe(df_fcf, hide_index=True, use_container_width=True)

            st.divider()
            interp = ("Intrinsic Value is the DCF-derived fair value per share. "
                      "If it is above the Current Price, the stock may be undervalued. "
                      "A BUY signal requires upside exceeding \u00b115% margin of safety; "
                      "SHORT requires downside exceeding \u00b115%. "
                      "WACC is the discount rate reflecting the company\u2019s cost of capital. "
                      "The Growth Rate is estimated from historical FCF using log-linear regression.")
            st.info(interp, icon=None)

# ──────────────── SCENARIOS TAB ────────────────

with tabs[1]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Run DCF first.")
    else:
        sc = run_scenarios(data, result)
        scol1, scol2, scol3 = st.columns(3)
        colors = {"bull": "#2d7d46", "base": "#4a8bc2", "bear": "#c0392b"}
        labels = {"bull": "Bull Case", "base": "Base Case", "bear": "Bear Case"}

        for name, col in zip(("bull", "base", "bear"), (scol1, scol2, scol3)):
            with col:
                s = sc[name]
                bg = colors[name]
                st.markdown(
                    f"<div style='background:{bg};padding:12px;border-radius:6px;color:white'>"
                    f"<h4 style='margin:0'>{labels[name]}</h4>"
                    f"<p><b>Intrinsic:</b> {fmt_currency(s['intrinsic'])}</p>"
                    f"<p><b>Upside:</b> {s['upside']:+.1%}</p>"
                    f"<p style='color:#ddd;font-size:0.9em'>"
                    f"Growth: {fmt_pct(s['growth'])} | "
                    f"WACC: {fmt_pct(s['wacc'])} | "
                    f"Term.G: {fmt_pct(s['terminal_g'])}"
                    f"</p></div>",
                    unsafe_allow_html=True,
                )

        st.divider()
        comp = pd.DataFrame([
            {"Scenario": k.title(), "Intrinsic": fmt_currency(v["intrinsic"]),
             "Upside": f"{v['upside']:+.1%}" if v['upside'] else "--",
             "Growth": fmt_pct(v["growth"]), "WACC": fmt_pct(v["wacc"])}
            for k, v in sc.items()
        ])
        st.dataframe(comp, hide_index=True, use_container_width=True)

        st.info(
            "Bull / Base / Bear cases stress-test the DCF by varying growth (1.5x / 1x / 0.5x of estimated growth), "
            "WACC (\u221210% / base / +10%), and terminal growth (\u00b120%). "
            "The spread between Bull and Bear shows the range of possible outcomes.",
            icon=None
        )

# ──────────────── IMPLIED G TAB ────────────────

with tabs[2]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Run DCF first.")
    else:
        price = data["price"]
        implied = implied_growth_rate(data, target_price=price, wacc=result["wacc"])
        estimated = result.get("estimated_growth", result["growth_rate"])

        st.metric("Current Price", fmt_currency(price))
        st.metric("WACC Used", fmt_pct(result["wacc"]))
        st.metric("Historical FCF Growth", fmt_pct(estimated))
        st.metric("Market-Implied Growth", fmt_pct(implied) if implied is not None else "Could not solve")

        if implied is not None and estimated:
            ratio = implied / estimated if estimated != 0 else float("inf")
            st.metric("Implied / Historical", f"{ratio:.1f}x")

        st.divider()
        txt = (
            "Market-Implied Growth is the FCF growth rate the current stock price is pricing in, "
            "solved by reverse-DCF (binary search). Compare it to the Historical FCF Growth "
            "(estimated from past cash flows)."
        )
        if implied is not None and estimated:
            if ratio > 1.5:
                txt += (
                    f"  Ratio: {ratio:.1f}x \u2014 The market expects much higher growth than "
                    "history suggests. The stock may be overvalued unless growth accelerates."
                )
            elif ratio < 0.5:
                txt += (
                    f"  Ratio: {ratio:.1f}x \u2014 The market prices in much lower growth than "
                    "history. The stock may be undervalued if the company can sustain its historical growth."
                )
            else:
                txt += (
                    f"  Ratio: {ratio:.1f}x \u2014 Market expectations ({fmt_pct(implied)}) are broadly "
                    f"in line with historical growth ({fmt_pct(estimated)})."
                )
        st.info(txt, icon=None)

# ──────────────── SENSITIVITY TAB ────────────────

with tabs[3]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Run DCF first.")
    else:
        data["_wacc"] = result["wacc"]
        sens = build_sensitivity(data)
        price = data["price"]

        mat = pd.DataFrame(
            sens["values"],
            index=[f"{w:.1%}" for w in sens["wacc_range"]],
            columns=[f"{t:.1%}" for t in sens["tg_range"]],
        )

        def _color_cell(val):
            if val is None or not price:
                return ""
            if val > price * 1.15:
                return "background-color: #2d7d46; color: white"
            if val < price * 0.85:
                return "background-color: #c0392b; color: white"
            return ""

        styled = mat.map(_color_cell).format(
            lambda v: fmt_currency(v) if pd.notna(v) else "--"
        )
        st.dataframe(styled, use_container_width=True)

        st.info(
            "Rows = WACC (discount rate), Columns = Terminal Growth Rate. "
            "Green cells indicate >15% upside vs current price (undervalued); "
            "red cells indicate >15% downside (overvalued).",
            icon=None
        )

# ──────────────── CHARTS TAB ────────────────

with tabs[4]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Run DCF first.")
    else:
        fig = build_fcf_figure(
            data["historical_fcfs"],
            result["projected_fcfs"],
            result["wacc"],
        )
        st.pyplot(fig)

        st.info(
            "Blue bars: historical free cash flows. Green bars: projected FCFs. "
            "Red dashed line: present value of projected FCFs \u2014 it declines each year because "
            "future cash flows are discounted at the WACC. All values in Cr (crores).",
            icon=None
        )

# ──────────────── RELATIVE VAL TAB ────────────────

with tabs[5]:
    result = st.session_state.last_result
    ticker_sym = st.session_state.last_ticker

    if not result:
        st.info("Run DCF first.")
    else:
        with st.spinner("Fetching historical data ..."):
            rd = get_percentiles(ticker_sym)

        if not rd:
            st.warning("Insufficient data for historical comparison.")
        else:
            rows = []
            labels = {"pe": "P/E", "pb": "P/B", "ps": "P/S", "ev_ebitda": "EV/EBITDA"}
            for key, label in labels.items():
                d = rd.get(key)
                if not d:
                    continue
                pct = d.get("pct")
                rows.append({
                    "Metric": label,
                    "Current": f"{d['current']:.1f}x" if d.get("current") else "--",
                    "3Y Low": f"{d['low']:.1f}x" if d.get("low") else "--",
                    "3Y High": f"{d['high']:.1f}x" if d.get("high") else "--",
                    "Percentile": f"{pct:.0%}" if pct is not None else "--",
                })
            df_rv = pd.DataFrame(rows)
            st.dataframe(df_rv, hide_index=True, use_container_width=True)

            st.info(
                "Percentile rank compares the current multiple to its own trailing 3-year range. "
                "0% = cheapest in 3 years; 100% = most expensive. "
                "A low percentile (<20%) may indicate a value opportunity; "
                "a high percentile (>80%) suggests the stock is expensive vs history.",
                icon=None
            )

# ──────────────── MONTE CARLO TAB ────────────────

with tabs[6]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    if not result:
        st.info("Run DCF first.")
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            mc_iters = st.number_input("Iterations", min_value=1000, max_value=50000,
                                        value=10000, step=1000)
        with col2:
            st.write("")
            run_mc = st.button("Run Monte Carlo", type="primary", use_container_width=True)

        if run_mc:
            data["_estimated_growth"] = result.get("estimated_growth", result["growth_rate"])
            data["_wacc"] = result["wacc"]

            with st.spinner(f"Running {mc_iters:,} iterations ..."):
                vals = run_monte_carlo(data, iterations=int(mc_iters))

            if vals:
                st.session_state.mc_results = vals
                st.rerun()

        if st.session_state.mc_results:
            vals = st.session_state.mc_results
            arr = np.array(vals)
            price = data["price"]

            fig = Figure(figsize=(7, 3.5), dpi=100)
            ax = fig.add_subplot(111)
            ax.hist(arr, bins=60, color="#4a8bc2", alpha=0.7, edgecolor="white")
            ax.axvline(price, color="red", linewidth=1.5, linestyle="--",
                       label=f"Current: {fmt_currency(price)}")
            ax.axvline(np.mean(arr), color="green", linewidth=1.2, linestyle="-",
                       label=f"Mean: {fmt_currency(np.mean(arr))}")
            ax.axvline(np.median(arr), color="orange", linewidth=1.2, linestyle=":",
                       label=f"Median: {fmt_currency(np.median(arr))}")
            ax.legend(fontsize=8)
            ax.set_title(f"Monte Carlo Distribution ({len(vals):,} iterations)", fontsize=10)
            ax.set_xlabel("Intrinsic Value", fontsize=9)
            ax.set_ylabel("Frequency", fontsize=9)
            fig.tight_layout()
            st.pyplot(fig)

            mc_stats = pd.DataFrame([
                {"Statistic": "Mean", "Value": fmt_currency(np.mean(arr))},
                {"Statistic": "Median", "Value": fmt_currency(np.median(arr))},
                {"Statistic": "Std Dev", "Value": fmt_currency(np.std(arr))},
                {"Statistic": "5th Percentile", "Value": fmt_currency(np.percentile(arr, 5))},
                {"Statistic": "95th Percentile", "Value": fmt_currency(np.percentile(arr, 95))},
                {"Statistic": "Current Price", "Value": fmt_currency(price)},
                {"Statistic": "P(Value \u2264 Price)",
                 "Value": f"{np.sum(arr <= price) / len(arr):.1%}"},
            ])
            st.dataframe(mc_stats, hide_index=True, use_container_width=True)

            st.info(
                "The histogram shows the distribution of possible intrinsic values from thousands "
                "of randomized DCF runs. Spread (Std Dev) reflects uncertainty. "
                "If Mean > Median, the distribution is right-skewed (upside potential exceeds downside risk). "
                "P(Value \u2264 Price) is the probability the stock is overvalued at the current price.",
                icon=None
            )

# ──────────────── WATCHLIST TAB ────────────────

with tabs[7]:
    wl = st.session_state.wl_tickers

    wcol1, wcol2, wcol3 = st.columns([1.5, 1, 3])
    with wcol1:
        wl_input = st.text_input("Add ticker", placeholder="e.g. RELIANCE", label_visibility="collapsed")
    with wcol2:
        add_clicked = st.button("Add", use_container_width=True)

    if add_clicked and wl_input:
        sym = wl_input.strip().upper()
        if "." not in sym:
            sym = sym + ".NS"
        if sym not in wl:
            wl.append(sym)
            st.session_state.wl_tickers = wl
            st.rerun()

    if wl:
        st.caption("Select a row and click Remove to delete.")

        # Refresh button
        refresh_wl = st.button("Refresh All", use_container_width=True, type="primary")

        wl_data = []
        if refresh_wl and wl:
            progress = st.progress(0, text="Fetching watchlist ...")
            for i, sym in enumerate(wl):
                try:
                    fcfs = get_financials(sym)
                    mkt = get_market_data(sym)
                    bs = get_balance_sheet(sym)
                    d = {
                        "historical_fcfs": fcfs,
                        "projection_years": 5,
                        "price": mkt["price"],
                        "shares_outstanding": mkt["shares_outstanding"],
                        "beta": mkt["beta"],
                        "market_cap": mkt["market_cap"],
                        "total_debt": bs["total_debt"],
                        "cash": bs["cash"],
                        "tax_rate": get_tax_rate(sym),
                        "rf_rate": get_risk_free_rate(),
                        "terminal_growth_rate": 0.04,
                    }
                    r = run_dcf(d, market_premium=0.07)
                    rec = analyze(r, d)
                    wl_data.append({
                        "Ticker": sym, "Price": fmt_currency(mkt["price"]),
                        "Intrinsic": fmt_currency(r["intrinsic_value"]),
                        "Upside": f"{r['upside']:+.1%}" if r.get("upside") else "--",
                        "Rec": rec["action"],
                    })
                except Exception as e:
                    wl_data.append({
                        "Ticker": sym, "Price": "--", "Intrinsic": "--",
                        "Upside": "--", "Rec": f"Error: {str(e)[:30]}",
                    })
                progress.progress((i + 1) / len(wl),
                                  text=f"Fetched {i+1}/{len(wl)}")
            st.session_state["_wl_data"] = wl_data
            st.rerun()

        # Show previously fetched data
        if "_wl_data" in st.session_state and st.session_state["_wl_data"]:
            wl_df = pd.DataFrame(st.session_state["_wl_data"])
            st.dataframe(wl_df, hide_index=True, use_container_width=True)

        remove_sym = st.selectbox("Remove ticker", options=[""] + wl)
        if remove_sym and st.button("Remove"):
            st.session_state.wl_tickers = [t for t in wl if t != remove_sym]
            st.session_state["_wl_data"] = [r for r in st.session_state.get("_wl_data", [])
                                             if r["Ticker"] != remove_sym]
            st.rerun()
    else:
        st.info("Watchlist is empty. Add tickers above.")

    st.caption("Tickers auto-append .NS (NSE). Refresh runs DCF sequentially for all tickers.")

# ──────────────── EXPORT TAB ────────────────

with tabs[8]:
    result = st.session_state.last_result
    data = st.session_state.last_data

    st.markdown("### Export DCF Report")

    export_sections = {}
    for sec in ["Valuation Summary", "Recommendation", "Cash Flow Table"]:
        export_sections[sec] = st.checkbox(sec, value=True)

    if result:
        csv_buffer = io.StringIO()
        export_csv(csv_buffer, result, data)
        csv_content = csv_buffer.getvalue()

        st.download_button(
            label="Download CSV",
            data=csv_content,
            file_name=f"dcf_report_{st.session_state.last_ticker}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )
    else:
        st.info("Run DCF first to export a report.")
        st.download_button(label="Download CSV", data="", disabled=True,
                           use_container_width=True)

    st.caption("Exports a CSV report. Only CSV format is supported.")

# ──────────────── RESEARCH REPORT ────────────────

if show_research and st.session_state.last_ticker:
    ticker_r = st.session_state.last_ticker
    with st.spinner("Loading research report ..."):
        report = generate_report(ticker_r)
    st.session_state.research_report = report

if st.session_state.research_report:
    with st.expander(f"Research Report \u2014 {st.session_state.last_ticker}", expanded=True):
        r = st.session_state.research_report
        view = st.radio("View", ["Summary", "Comprehensive"], horizontal=True)

        prof = r.get("profile", {})
        st.markdown(f"**{prof.get('name')}**  \u2014  {prof.get('sector')} / {prof.get('industry')}")

        if view == "Summary":
            val = r.get("valuation", {})
            mom = r.get("momentum", {})
            margins = r.get("margins", {})

            scol1, scol2, scol3 = st.columns(3)
            with scol1:
                st.metric("P/E (Trailing)", f"{val.get('pe_trailing', '--'):.1f}x" if val.get("pe_trailing") else "--")
                st.metric("P/B", f"{val.get('pb', '--'):.1f}x" if val.get("pb") else "--")
            with scol2:
                st.metric("P/S", f"{val.get('ps', '--'):.1f}x" if val.get("ps") else "--")
                st.metric("Div Yield", f"{val.get('dividend_yield', 0) * 100:.1%}" if val.get("dividend_yield") else "--")
            with scol3:
                st.metric("RSI (14)", f"{mom.get('rsi', '--'):.1f}" if mom.get("rsi") else "--")
                st.metric("12M Return", f"{mom.get('return_12m', 0) * 100:.1%}" if mom.get("return_12m") else "--")

            if margins:
                latest_yr = max(margins.keys())
                m = margins[latest_yr]
                st.markdown(f"**Latest Margins ({latest_yr})**")
                st.metric("Gross", f"{m['gross']*100:.1%}" if m.get("gross") else "--")
                st.metric("Operating", f"{m['operating']*100:.1%}" if m.get("operating") else "--")
                st.metric("Net", f"{m['net']*100:.1%}" if m.get("net") else "--")

        else:
            # Comprehensive
            with st.expander("Company Profile", expanded=True):
                st.markdown(f"**Employees:** {prof.get('employees', '--')}  \u2014  "
                           f"**Country:** {prof.get('country', '--')}")
                if prof.get("website"):
                    st.markdown(f"**Website:** {prof['website']}")
                if prof.get("description"):
                    with st.container():
                        st.markdown("**Description**")
                        st.write(prof["description"])

            margins_data = r.get("margins", {})
            if margins_data:
                st.subheader("Profitability Trends (5 Years)")
                mdf = pd.DataFrame([
                    {"Year": yr, "Gross": f"{m['gross']*100:.1%}" if m.get("gross") else "--",
                     "Operating": f"{m['operating']*100:.1%}" if m.get("operating") else "--",
                     "Net": f"{m['net']*100:.1%}" if m.get("net") else "--"}
                    for yr, m in sorted(margins_data.items())
                ])
                st.dataframe(mdf, hide_index=True, use_container_width=True)

            health = r.get("health", {})
            st.subheader("Financial Health")
            hdf = pd.DataFrame([
                {"Ratio": "ROE", "Value": f"{health['roe']*100:.1%}" if health.get("roe") else "--"},
                {"Ratio": "ROA", "Value": f"{health['roa']*100:.1%}" if health.get("roa") else "--"},
                {"Ratio": "Debt / Equity", "Value": f"{health['debt_equity']:.2f}" if health.get("debt_equity") else "--"},
                {"Ratio": "Current Ratio", "Value": f"{health['current_ratio']:.2f}" if health.get("current_ratio") else "--"},
                {"Ratio": "Interest Coverage", "Value": f"{health['interest_coverage']:.1f}" if health.get("interest_coverage") else "--"},
            ])
            st.dataframe(hdf, hide_index=True, use_container_width=True)

            growth = r.get("growth", {})
            st.subheader("Growth Rates")
            gdf = pd.DataFrame([
                {"Metric": "Revenue CAGR (3Y)", "Value": f"{growth['revenue_cagr_3y']*100:.1%}" if growth.get("revenue_cagr_3y") else "--"},
                {"Metric": "Revenue CAGR (5Y)", "Value": f"{growth['revenue_cagr_5y']*100:.1%}" if growth.get("revenue_cagr_5y") else "--"},
                {"Metric": "Earnings CAGR (3Y)", "Value": f"{growth['earnings_cagr_3y']*100:.1%}" if growth.get("earnings_cagr_3y") else "--"},
                {"Metric": "Earnings CAGR (5Y)", "Value": f"{growth['earnings_cagr_5y']*100:.1%}" if growth.get("earnings_cagr_5y") else "--"},
            ])
            st.dataframe(gdf, hide_index=True, use_container_width=True)

            val_full = r.get("valuation", {})
            st.subheader("Valuation Multiples")
            vdf = pd.DataFrame([
                {"Metric": "P/E (Trailing)", "Value": f"{val_full['pe_trailing']:.1f}x" if val_full.get("pe_trailing") else "--"},
                {"Metric": "P/E (Forward)", "Value": f"{val_full['pe_forward']:.1f}x" if val_full.get("pe_forward") else "--"},
                {"Metric": "P/B", "Value": f"{val_full['pb']:.1f}x" if val_full.get("pb") else "--"},
                {"Metric": "P/S", "Value": f"{val_full['ps']:.1f}x" if val_full.get("ps") else "--"},
                {"Metric": "EV/EBITDA", "Value": f"{val_full['ev_ebitda']:.1f}x" if val_full.get("ev_ebitda") else "--"},
                {"Metric": "Dividend Yield", "Value": f"{val_full['dividend_yield']*100:.1%}" if val_full.get("dividend_yield") else "--"},
                {"Metric": "Market Cap", "Value": fmt_currency(val_full.get("market_cap"))},
            ])
            st.dataframe(vdf, hide_index=True, use_container_width=True)

            mom_full = r.get("momentum", {})
            st.subheader("Momentum & Risk")
            momdf = pd.DataFrame([
                {"Metric": "52-Week High", "Value": fmt_currency(mom_full.get("high_52w"))},
                {"Metric": "52-Week Low", "Value": fmt_currency(mom_full.get("low_52w"))},
                {"Metric": "1M Return", "Value": f"{mom_full['return_1m']*100:.1%}" if mom_full.get("return_1m") else "--"},
                {"Metric": "3M Return", "Value": f"{mom_full['return_3m']*100:.1%}" if mom_full.get("return_3m") else "--"},
                {"Metric": "6M Return", "Value": f"{mom_full['return_6m']*100:.1%}" if mom_full.get("return_6m") else "--"},
                {"Metric": "12M Return", "Value": f"{mom_full['return_12m']*100:.1%}" if mom_full.get("return_12m") else "--"},
                {"Metric": "RSI (14)", "Value": f"{mom_full['rsi']:.1f}" if mom_full.get("rsi") else "--"},
                {"Metric": "Beta", "Value": f"{mom_full['beta']:.3f}" if mom_full.get("beta") else "--"},
            ])
            st.dataframe(momdf, hide_index=True, use_container_width=True)
