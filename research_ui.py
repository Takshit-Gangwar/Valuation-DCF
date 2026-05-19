import tkinter as tk
from tkinter import ttk


def _fmt(v, pct=False):
    if v is None:
        return "--"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v:,.2f}"


def _pct(v):
    if v is None:
        return "--"
    return f"{v * 100:.1f}%"


def _kv_grid(parent, pairs, start_row=0):
    r = start_row
    for label, value in pairs:
        ttk.Label(parent, text=label + ":", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, sticky=tk.W, padx=8, pady=1)
        ttk.Label(parent, text=value if value is not None else "--",
                  font=("Segoe UI", 9)).grid(row=r, column=1, sticky=tk.W, padx=8, pady=1)
        r += 1
    return r


def build_summary(parent, r):
    frame = ttk.LabelFrame(parent, text="Company Overview", padding=8)
    frame._section = "summary"
    frame.pack(fill=tk.X, padx=10, pady=(10, 0))

    prof = r.get("profile", {})
    rows = [
        ("Name", prof.get("name")),
        ("Sector", prof.get("sector")),
        ("Industry", prof.get("industry")),
    ]
    _kv_grid(frame, rows)

    # ── Valuation quick view ──
    vframe = ttk.LabelFrame(parent, text="Valuation Snapshot", padding=8)
    vframe._section = "summary"
    vframe.pack(fill=tk.X, padx=10, pady=(10, 0))

    val = r.get("valuation", {})
    val_rows = [
        ("P/E (Trailing)", _fmt(val.get("pe_trailing"))),
        ("P/E (Forward)", _fmt(val.get("pe_forward"))),
        ("P/B", _fmt(val.get("pb"))),
        ("P/S", _fmt(val.get("ps"))),
        ("Div Yield", _pct(val.get("dividend_yield"))),
    ]
    _kv_grid(vframe, val_rows)

    # ── Momentum quick view ──
    mframe = ttk.LabelFrame(parent, text="Momentum", padding=8)
    mframe._section = "summary"
    mframe.pack(fill=tk.X, padx=10, pady=(10, 0))

    mom = r.get("momentum", {})
    mom_rows = [
        ("RSI (14)", _fmt(mom.get("rsi"))),
        ("1M Return", _pct(mom.get("return_1m"))),
        ("3M Return", _pct(mom.get("return_3m"))),
        ("6M Return", _pct(mom.get("return_6m"))),
        ("12M Return", _pct(mom.get("return_12m"))),
    ]
    _kv_grid(mframe, mom_rows)

    # ── Profitability snapshot ──
    pframe = ttk.LabelFrame(parent, text="Profitability", padding=8)
    pframe._section = "summary"
    pframe.pack(fill=tk.X, padx=10, pady=(10, 0))

    margins = r.get("margins", {})
    if margins:
        latest_yr = max(margins.keys())
        m = margins[latest_yr]
        prof_rows = [
            ("Gross Margin", _pct(m.get("gross"))),
            ("Operating Margin", _pct(m.get("operating"))),
            ("Net Margin", _pct(m.get("net"))),
        ]
        _kv_grid(pframe, prof_rows)


def build_comprehensive(parent, r):
    # ── Full Company Profile ──
    frame = ttk.LabelFrame(parent, text="Company Profile", padding=8)
    frame._section = "comprehensive"
    frame.pack(fill=tk.X, padx=10, pady=(0, 8))

    prof = r.get("profile", {})
    rows = [
        ("Name", prof.get("name")),
        ("Sector", prof.get("sector")),
        ("Industry", prof.get("industry")),
        ("Employees", _fmt(prof.get("employees"))),
        ("Country", prof.get("country")),
        ("Website", prof.get("website")),
    ]
    _kv_grid(frame, rows)

    desc = prof.get("description")
    if desc:
        desc_frame = ttk.Frame(frame)
        desc_frame.grid(row=len(rows), column=0, columnspan=2, sticky=tk.W, padx=8, pady=4)
        ttk.Label(desc_frame, text="Description:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        text_widget = tk.Text(desc_frame, height=4, wrap=tk.WORD, font=("Segoe UI", 9),
                              borderwidth=0, relief=tk.FLAT)
        text_widget.insert(tk.END, desc)
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill=tk.X, padx=(0, 8))

    # ── 5-Year Profitability Trends ──
    tframe = ttk.LabelFrame(parent, text="Profitability Trends (5 Years)", padding=8)
    tframe._section = "comprehensive"
    tframe.pack(fill=tk.X, padx=10, pady=(0, 8))

    margins = r.get("margins", {})
    years = sorted(margins.keys())
    tree = ttk.Treeview(tframe, columns=("year", "gross", "operating", "net"),
                        show="headings", height=6)
    tree.heading("year", text="Year")
    tree.heading("gross", text="Gross")
    tree.heading("operating", text="Operating")
    tree.heading("net", text="Net")
    tree.column("year", width=60)
    tree.column("gross", width=90)
    tree.column("operating", width=90)
    tree.column("net", width=90)
    for yr in years:
        m = margins[yr]
        tree.insert("", tk.END, values=(
            str(yr),
            _pct(m.get("gross")),
            _pct(m.get("operating")),
            _pct(m.get("net")),
        ))
    tree.pack(fill=tk.X, padx=4, pady=4)

    # ── Financial Health ──
    hframe = ttk.LabelFrame(parent, text="Financial Health", padding=8)
    hframe._section = "comprehensive"
    hframe.pack(fill=tk.X, padx=10, pady=(0, 8))

    h = r.get("health", {})
    health_rows = [
        ("ROE", _pct(h.get("roe"))),
        ("ROA", _pct(h.get("roa"))),
        ("Debt / Equity", _fmt(h.get("debt_equity"))),
        ("Current Ratio", _fmt(h.get("current_ratio"))),
        ("Interest Coverage", _fmt(h.get("interest_coverage"))),
    ]
    _kv_grid(hframe, health_rows)

    # ── Growth Rates ──
    gframe = ttk.LabelFrame(parent, text="Growth Rates", padding=8)
    gframe._section = "comprehensive"
    gframe.pack(fill=tk.X, padx=10, pady=(0, 8))

    g = r.get("growth", {})
    growth_rows = [
        ("Revenue CAGR (3Y)", _pct(g.get("revenue_cagr_3y"))),
        ("Revenue CAGR (5Y)", _pct(g.get("revenue_cagr_5y"))),
        ("Earnings CAGR (3Y)", _pct(g.get("earnings_cagr_3y"))),
        ("Earnings CAGR (5Y)", _pct(g.get("earnings_cagr_5y"))),
    ]
    _kv_grid(gframe, growth_rows)

    # ── Valuation Multiples ──
    valframe = ttk.LabelFrame(parent, text="Valuation Multiples", padding=8)
    valframe._section = "comprehensive"
    valframe.pack(fill=tk.X, padx=10, pady=(0, 8))

    val = r.get("valuation", {})
    val_rows = [
        ("P/E (Trailing)", _fmt(val.get("pe_trailing"))),
        ("P/E (Forward)", _fmt(val.get("pe_forward"))),
        ("P/B", _fmt(val.get("pb"))),
        ("P/S", _fmt(val.get("ps"))),
        ("EV / EBITDA", _fmt(val.get("ev_ebitda"))),
        ("Dividend Yield", _pct(val.get("dividend_yield"))),
        ("Payout Ratio", _pct(val.get("payout_ratio"))),
        ("Market Cap", _fmt(val.get("market_cap"))),
    ]
    _kv_grid(valframe, val_rows)

    # ── Momentum & Risk ──
    mframe = ttk.LabelFrame(parent, text="Momentum & Risk", padding=8)
    mframe._section = "comprehensive"
    mframe.pack(fill=tk.X, padx=10, pady=(0, 8))

    mom = r.get("momentum", {})
    momentum_rows = [
        ("52-Week High", _fmt(mom.get("high_52w"))),
        ("52-Week Low", _fmt(mom.get("low_52w"))),
        ("1M Return", _pct(mom.get("return_1m"))),
        ("3M Return", _pct(mom.get("return_3m"))),
        ("6M Return", _pct(mom.get("return_6m"))),
        ("12M Return", _pct(mom.get("return_12m"))),
        ("RSI (14)", _fmt(mom.get("rsi"))),
        ("Beta", _fmt(mom.get("beta"))),
    ]
    _kv_grid(mframe, momentum_rows)
