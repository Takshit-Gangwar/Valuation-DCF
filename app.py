import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import numpy as np
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
from portfolio import Portfolio
from export import export_csv


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


def _fmt_big(v):
    if v is None:
        return "--"
    if abs(v) >= 1e7:
        return f"{v / 1e7:,.2f} Cr"
    if abs(v) >= 1e5:
        return f"{v / 1e5:,.2f} L"
    return f"{v:,.2f}"


def _bind_mousewheel(canvas):
    def _on_mw(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mw)
    canvas.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))


def _kv_row(parent, label, value, col=0):
    r = parent.grid_size()[1]
    ttk.Label(parent, text=label + ":", font=("Segoe UI", 9, "bold")).grid(
        row=r, column=0, sticky=tk.W, padx=5, pady=1)
    ttk.Label(parent, text=str(value) if value is not None else "--",
              font=("Segoe UI", 9)).grid(row=r, column=1, sticky=tk.W, padx=10, pady=1)


class AutocompleteEntry(ttk.Entry):
    def __init__(self, master, search_fn, **kwargs):
        super().__init__(master, **kwargs)
        self._search_fn = search_fn
        self._listbox = None
        self._search_after = None
        self._search_seq = 0
        self.bind("<KeyRelease>", self._on_keyrelease)
        self.bind("<FocusOut>", lambda e: self.after(150, self._hide))
        self.bind("<Down>", self._on_down)

    def _hide(self):
        if self._listbox:
            self._listbox.place_forget()

    def _show(self, suggestions):
        self._search_seq += 1
        if not suggestions:
            self._hide()
            return
        lb = self._listbox
        if lb is None:
            root = self.winfo_toplevel()
            lb = tk.Listbox(root, height=6, activestyle="none",
                            font=("Segoe UI", 10), exportselection=False,
                            borderwidth=1, relief=tk.SOLID)
            lb.bind("<ButtonRelease-1>", self._on_select)
            lb.bind("<Return>", self._on_select)
            lb.bind("<Escape>", lambda e: self._hide())
            lb.bind("<FocusOut>", lambda e: self.after(50, self._hide))
            self._listbox = lb
        lb.delete(0, tk.END)
        for s in suggestions:
            label = f"{s['symbol']:12s}  {s['name']}"
            lb.insert(tk.END, label)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        lb.place(x=x, y=y, width=max(self.winfo_width() + 220, 300))
        lb.lift()
        lb.tkraise()

    def _select_active(self):
        lb = self._listbox
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        symbol = lb.get(sel[0]).split()[0]
        self.delete(0, tk.END)
        self.insert(0, symbol)
        self._hide()
        self.icursor(tk.END)
        self.event_generate("<<AutocompleteSelect>>")

    def _on_keyrelease(self, event):
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape"):
            return
        if event.keysym == "BackSpace" and self.get() == "":
            self._hide()
            return
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(300, self._do_search)

    def _do_search(self):
        query = self.get().strip()
        if len(query) < 1:
            self._hide()
            return
        seq = self._search_seq
        results = self._search_fn(query)
        self.after(0, self._on_results, seq, results)

    def _on_results(self, seq, results):
        if seq != self._search_seq:
            return
        self._show(results)

    def _on_down(self, event):
        lb = self._listbox
        if lb and lb.winfo_ismapped():
            lb.focus_set()
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)
            lb.activate(0)
            return "break"

    def _on_select(self, event):
        if self._listbox is None:
            return
        if event.type == tk.EventType.ButtonRelease:
            self.after(50, self._select_active)
        else:
            self._select_active()


class DCFApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DCF Stock Valuation Model")
        self.root.geometry("1060x720")
        self.root.minsize(900, 600)

        self._fetched_data = {}
        self._last_ticker = None
        self._last_result = None
        self._last_data = None
        self.currency_sym = "Rs"
        self.portfolio = Portfolio()

        self._build_top_bar()
        self._build_notebook()
        self._build_status_bar()

    # ── Top bar ──
    def _build_top_bar(self):
        top = ttk.Frame(self.root, padding="8")
        top.pack(fill=tk.X)

        ttk.Label(top, text="Ticker:").pack(side=tk.LEFT, padx=(0, 5))
        self.ticker_entry = AutocompleteEntry(top, search_fn=search_tickers,
                                              width=25, font=("Segoe UI", 11))
        self.ticker_entry.pack(side=tk.LEFT, padx=(0, 8))
        self.ticker_entry.bind("<Return>", lambda e: self.calculate())
        self.ticker_entry.bind("<<AutocompleteSelect>>", lambda e: self.calculate())

        self.calc_btn = ttk.Button(top, text="Calculate", command=self.calculate)
        self.calc_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.research_btn = ttk.Button(top, text="Research", command=self._open_research, state=tk.DISABLED)
        self.research_btn.pack(side=tk.LEFT)

    # ── Notebook ──
    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self.tabs = {}
        tab_ids = [
            ("DCF", "_build_dcf_tab"),
            ("Scenarios", "_build_scenarios_tab"),
            ("Implied G", "_build_implied_tab"),
            ("Sensitivity", "_build_sensitivity_tab"),
            ("Charts", "_build_charts_tab"),
            ("Rel Val", "_build_relval_tab"),
            ("Monte Carlo", "_build_monte_carlo_tab"),
            ("Watchlist", "_build_watchlist_tab"),
            ("Export", "_build_export_tab"),
        ]
        for label, method_name in tab_ids:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=label)
            getattr(self, method_name)(frame)
            self.tabs[label] = frame

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        tab = self.notebook.select()
        if not tab:
            return
        tab_name = self.notebook.tab(tab, "text")
        if tab_name != "DCF":
            self._refresh_active_tab(tab_name)

    def _refresh_active_tab(self, name):
        if not self._last_result:
            return
        method_name = f"_update_{name.lower().replace(' ', '_')}_tab"
        method = getattr(self, method_name, None)
        if method:
            method()

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Ready")
        bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ── DCF Tab (core) ──
    def _build_dcf_tab(self, parent):
        settings = ttk.LabelFrame(parent, text="Settings", padding="8")
        settings.pack(fill=tk.X, padx=6, pady=4)

        ttk.Label(settings, text="Projection Years:").grid(row=0, column=0, sticky=tk.W, padx=(0, 4))
        self.years_var = tk.IntVar(value=5)
        ttk.Spinbox(settings, from_=3, to=20, textvariable=self.years_var, width=5).grid(
            row=0, column=1, sticky=tk.W, padx=(0, 18))

        ttk.Label(settings, text="Discount Rate (WACC %):").grid(row=0, column=2, sticky=tk.W, padx=(0, 4))
        self.wacc_var = tk.StringVar(value="Auto")
        ttk.Entry(settings, textvariable=self.wacc_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=(0, 4))
        ttk.Label(settings, text="(Auto)").grid(row=0, column=4, sticky=tk.W, padx=(0, 18))

        ttk.Label(settings, text="Terminal Growth %:").grid(row=0, column=5, sticky=tk.W, padx=(0, 4))
        self.term_g_var = tk.StringVar(value="4.0")
        ttk.Entry(settings, textvariable=self.term_g_var, width=8).grid(row=0, column=6, sticky=tk.W)

        body = ttk.Frame(parent)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        res_frame = ttk.LabelFrame(left, text="Valuation Results", padding="8")
        res_frame.pack(fill=tk.BOTH, expand=True)

        self._rec_frame = tk.Frame(res_frame, padx=10, pady=4)
        self._rec_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))
        self._rec_frame.grid_remove()
        self._rec_action = tk.Label(self._rec_frame, font=("Segoe UI", 12, "bold"), anchor=tk.W)
        self._rec_action.pack(fill=tk.X)
        self._rec_summary = tk.Label(self._rec_frame, font=("Segoe UI", 9), anchor=tk.W, wraplength=380)
        self._rec_summary.pack(fill=tk.X)
        self._rec_reasons = tk.Label(self._rec_frame, font=("Segoe UI", 8), anchor=tk.W, wraplength=380, justify=tk.LEFT)
        self._rec_reasons.pack(fill=tk.X)

        self._result_labels = {}
        rows = [
            ("Intrinsic Value / Share", "intrinsic"),
            ("Current Price", "price"),
            ("Upside / Downside", "upside"),
            (None, None),
            ("Estimated Growth Rate", "growth_rate"),
            ("WACC (Discount Rate)", "wacc"),
            ("Terminal Value", "terminal_value"),
            ("Enterprise Value", "enterprise_value"),
            ("Equity Value", "equity_value"),
        ]
        for i, (label, key) in enumerate(rows):
            row = i + 1
            if label is None:
                ttk.Separator(res_frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
                continue
            bold = key in ("intrinsic", "price", "upside")
            ttk.Label(res_frame, text=f"{label}:", font=("Segoe UI", 10, "bold" if bold else "normal")).grid(
                row=row, column=0, sticky=tk.W, padx=4, pady=1)
            val = ttk.Label(res_frame, text="--", font=("Segoe UI", 10, "bold" if bold else "normal"))
            val.grid(row=row, column=1, sticky=tk.W, padx=8, pady=1)
            self._result_labels[key] = val

        right = ttk.LabelFrame(body, text="Cash Flow Projections", padding="4")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(8, 0))

        columns = ("year", "historical", "projected")
        self.tree = ttk.Treeview(right, columns=columns, show="headings", height=16)
        self.tree.heading("year", text="Year")
        self.tree.heading("historical", text="Historical FCF (Rs)")
        self.tree.heading("projected", text="Projected FCF (Rs)")
        self.tree.column("year", width=65, anchor=tk.CENTER)
        self.tree.column("historical", width=130, anchor=tk.E)
        self.tree.column("projected", width=130, anchor=tk.E)
        scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        interp = ttk.LabelFrame(parent, text="Interpretation", padding=8)
        interp.pack(fill=tk.X, padx=6, pady=(0, 4))
        ttk.Label(interp, text=(
            "Intrinsic Value is the DCF-derived fair value per share. "
            "If it is above the Current Price, the stock may be undervalued. "
            "A BUY signal requires upside exceeding the \u00b115% margin of safety; "
            "SHORT requires downside exceeding \u00b115%. "
            "WACC is the discount rate reflecting the company\u2019s cost of capital. "
            "The Growth Rate is estimated from historical FCF using log-linear regression."
        ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

    # ── Scenario Analysis Tab ──
    def _build_scenarios_tab(self, parent):
        self._scenarios_frame = ttk.Frame(parent)
        self._scenarios_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _update_scenarios_tab(self):
        for w in self._scenarios_frame.winfo_children():
            w.destroy()
        result, data = self._last_result, self._last_data
        if not result:
            ttk.Label(self._scenarios_frame, text="Run DCF first").pack(pady=50)
            return
        sc = run_scenarios(data, result)

        cards_frame = ttk.Frame(self._scenarios_frame)
        cards_frame.pack(fill=tk.X)
        colors = {'bull': '#2d7d46', 'base': '#4a8bc2', 'bear': '#c0392b'}
        labels = {'bull': 'Bull Case', 'base': 'Base Case', 'bear': 'Bear Case'}

        for name in ('bull', 'base', 'bear'):
            card = tk.Frame(cards_frame, bg=colors[name], padx=12, pady=8,
                            highlightbackground="#ccc", highlightthickness=1)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            s = sc[name]
            tk.Label(card, text=labels[name], font=("Segoe UI", 11, "bold"),
                     bg=colors[name], fg="white").pack(anchor=tk.W)
            tk.Label(card, text=f"Intrinsic: {fmt_currency(s['intrinsic'])}",
                     font=("Segoe UI", 10), bg=colors[name], fg="white").pack(anchor=tk.W)
            up = s['upside']
            tk.Label(card, text=f"Upside: {up:+.1%}" if up else "Upside: --",
                     font=("Segoe UI", 10), bg=colors[name], fg="white").pack(anchor=tk.W)
            tk.Label(card, text=f"Growth: {fmt_pct(s['growth'])}",
                     font=("Segoe UI", 9), bg=colors[name], fg="#ddd").pack(anchor=tk.W)
            tk.Label(card, text=f"WACC: {fmt_pct(s['wacc'])}",
                     font=("Segoe UI", 9), bg=colors[name], fg="#ddd").pack(anchor=tk.W)
            tk.Label(card, text=f"Terminal G: {fmt_pct(s['terminal_g'])}",
                     font=("Segoe UI", 9), bg=colors[name], fg="#ddd").pack(anchor=tk.W)

        ttk.Label(self._scenarios_frame, text="").pack()
        comp = ttk.LabelFrame(self._scenarios_frame, text="Comparison", padding=8)
        comp.pack(fill=tk.X)
        cols = ("scenario", "intrinsic", "upside", "growth", "wacc")
        tv = ttk.Treeview(comp, columns=cols, show="headings", height=4)
        for c in cols:
            tv.heading(c, text=c.replace('_', ' ').title())
        tv.column("scenario", width=100)
        tv.column("intrinsic", width=130, anchor=tk.E)
        tv.column("upside", width=100, anchor=tk.E)
        tv.column("growth", width=100, anchor=tk.E)
        tv.column("wacc", width=100, anchor=tk.E)
        for name in ('bull', 'base', 'bear'):
            s = sc[name]
            tv.insert("", tk.END, values=(
                name.title(),
                fmt_currency(s['intrinsic']),
                f"{s['upside']:+.1%}" if s['upside'] else "--",
                fmt_pct(s['growth']),
                fmt_pct(s['wacc']),
            ))
        tv.pack(fill=tk.X)

        interp = ttk.LabelFrame(self._scenarios_frame, text="Interpretation", padding=8)
        interp.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(interp, text=(
            "Bull / Base / Bear cases stress-test the DCF by varying growth (1.5x / 1x / 0.5x of estimated growth), "
            "WACC (\u221210% / base / +10%), and terminal growth (\u00b120%). "
            "The spread between Bull and Bear shows the range of possible outcomes under different assumptions. "
            "Use this to assess how sensitive the valuation is to input changes."
        ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

    # ── Implied Growth Tab ──
    def _build_implied_tab(self, parent):
        self._implied_frame = ttk.Frame(parent)
        self._implied_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _update_implied_g_tab(self):
        for w in self._implied_frame.winfo_children():
            w.destroy()
        result, data = self._last_result, self._last_data
        if not result:
            ttk.Label(self._implied_frame, text="Run DCF first").pack(pady=50)
            return
        price = data['price']
        implied = implied_growth_rate(data, target_price=price, wacc=result['wacc'])
        estimated = result.get('estimated_growth', result['growth_rate'])

        info = ttk.LabelFrame(self._implied_frame, text="Implied Growth Rate", padding=12)
        info.pack(fill=tk.X, pady=10)

        _kv_row(info, "Current Price", fmt_currency(price))
        _kv_row(info, "WACC Used", fmt_pct(result['wacc']))
        _kv_row(info, "Historical FCF Growth", fmt_pct(estimated))
        _kv_row(info, "Market-Implied Growth", fmt_pct(implied) if implied else "Could not solve")
        if implied and estimated:
            ratio = implied / estimated if estimated != 0 else float('inf')
            _kv_row(info, "Implied / Historical", f"{ratio:.1f}x")

        interp = ttk.LabelFrame(self._implied_frame, text="Interpretation", padding=8)
        interp.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(interp, text=(
            "Market-Implied Growth is the FCF growth rate the current stock price is pricing in, "
            "solved by reverse-DCF (binary search). Compare it to the Historical FCF Growth "
            "(estimated from past cash flows)."
        ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)
        if implied and estimated:
            if ratio > 1.5:
                text = (f"Ratio: {ratio:.1f}x \u2014 The market expects much higher growth than history suggests. "
                        "The stock may be overvalued unless growth accelerates.")
            elif ratio < 0.5:
                text = (f"Ratio: {ratio:.1f}x \u2014 The market prices in much lower growth than history. "
                        "The stock may be undervalued if the company can sustain its historical growth.")
            else:
                text = (f"Ratio: {ratio:.1f}x \u2014 Market expectations ({fmt_pct(implied)}) are broadly in line with "
                        f"historical growth ({fmt_pct(estimated)}). The price appears reasonable relative to past performance.")
            ttk.Label(interp, text=text, wraplength=900, font=("Segoe UI", 9),
                      foreground="#555").pack(anchor=tk.W, pady=(4, 0))

    # ── Sensitivity Tab ──
    def _build_sensitivity_tab(self, parent):
        self._sens_frame = ttk.Frame(parent)
        self._sens_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _update_sensitivity_tab(self):
        for w in self._sens_frame.winfo_children():
            w.destroy()
        result, data = self._last_result, self._last_data
        if not result or not data:
            ttk.Label(self._sens_frame, text="Run DCF first").pack(pady=50)
            return
        data['_wacc'] = result['wacc']
        sens = build_sensitivity(data)
        price = data['price']

        cols = ["WACC \\ TG"] + [f"{tg:.1%}" for tg in sens['tg_range']]
        tv = ttk.Treeview(self._sens_frame, columns=cols, show="headings", height=len(sens['wacc_range']))
        tv.heading("WACC \\ TG", text="WACC \\ TG")
        for c in cols[1:]:
            tv.heading(c, text=c)
        tv.column("WACC \\ TG", width=100, anchor=tk.CENTER)
        for c in cols[1:]:
            tv.column(c, width=110, anchor=tk.E)

        style = ttk.Style()
        style.theme_use("default")

        for i, w in enumerate(sens['wacc_range']):
            row_vals = [f"{w:.1%}"]
            for j, iv in enumerate(sens['values'][i]):
                if iv is None:
                    row_vals.append("--")
                else:
                    txt = fmt_currency(iv)
                    row_vals.append(txt)
            item = tv.insert("", tk.END, values=row_vals)
            # Color coding
            tags = []
            for j, iv in enumerate(sens['values'][i]):
                if iv is not None and price:
                    if iv > price * 1.15:
                        tags.append(f"green_{j}")
                    elif iv < price * 0.85:
                        tags.append(f"red_{j}")
            tv.item(item, tags=tags)

        tv.pack(fill=tk.BOTH, expand=True, pady=8)

        interp = ttk.LabelFrame(self._sens_frame, text="Interpretation", padding=8)
        interp.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(interp, text=(
            "Rows = WACC (discount rate), Columns = Terminal Growth Rate. "
            "Each cell shows the intrinsic value for that combination of assumptions. "
            "Green cells indicate >15% upside vs current price (undervalued); "
            "red cells indicate >15% downside (overvalued). "
            "A wide spread across the matrix means the valuation is highly sensitive to these inputs."
        ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

    # ── Charts Tab ──
    def _build_charts_tab(self, parent):
        self._charts_frame = ttk.Frame(parent)
        self._charts_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _update_charts_tab(self):
        for w in self._charts_frame.winfo_children():
            w.destroy()
        result, data = self._last_result, self._last_data
        if not result:
            ttk.Label(self._charts_frame, text="Run DCF first").pack(pady=50)
            return

        from visualization import build_fcf_chart
        widget = build_fcf_chart(
            self._charts_frame,
            data['historical_fcfs'],
            result['projected_fcfs'],
            result['wacc'],
            self.currency_sym,
        )
        widget.pack(fill=tk.BOTH, expand=True)

        interp = ttk.LabelFrame(self._charts_frame, text="Interpretation", padding=8)
        interp.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(interp, text=(
            "Blue bars: historical free cash flows. Green bars: projected (forecast) FCFs. "
            "Red dashed line: present value of projected FCFs \u2014 it declines each year because "
            "future cash flows are discounted at the WACC. All values are in Cr (crores). "
            "The chart helps visualize how much of the DCF value comes from near-term vs distant cash flows."
        ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

    # ── Relative Valuation Tab ──
    def _build_relval_tab(self, parent):
        self._relval_frame = ttk.Frame(parent)
        self._relval_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _update_rel_val_tab(self):
        for w in self._relval_frame.winfo_children():
            w.destroy()
        result = self._last_result
        if not result:
            ttk.Label(self._relval_frame, text="Run DCF first").pack(pady=50)
            return

        status = ttk.Label(self._relval_frame, text="Fetching historical data ...",
                           font=("Segoe UI", 10))
        status.pack(pady=20)

        def fetch():
            try:
                from relative_val import get_percentiles
                ticker = self._last_ticker
                rd = get_percentiles(ticker)
                self.root.after(0, _display, rd)
            except Exception as e:
                self.root.after(0, lambda: (status.config(text=f"Error: {e}")))

        def _display(rd):
            status.destroy()
            if not rd:
                ttk.Label(self._relval_frame, text="Insufficient data for historical comparison.").pack(pady=30)
                return
            cols = ("metric", "current", "3yr_low", "3yr_high", "percentile")
            tv = ttk.Treeview(self._relval_frame, columns=cols, show="headings", height=8)
            for c in cols:
                tv.heading(c, text=c.replace('_', ' ').title())
            tv.column("metric", width=120)
            tv.column("current", width=100, anchor=tk.E)
            tv.column("3yr_low", width=100, anchor=tk.E)
            tv.column("3yr_high", width=100, anchor=tk.E)
            tv.column("percentile", width=100, anchor=tk.CENTER)

            labels = {'pe': 'P/E', 'pb': 'P/B', 'ps': 'P/S', 'ev_ebitda': 'EV/EBITDA'}
            for key, label in labels.items():
                d = rd.get(key)
                if not d:
                    continue
                pct = d.get('pct')
                pct_str = f"{pct:.0%}" if pct is not None else "--"
                tv.insert("", tk.END, values=(
                    label,
                    f"{d['current']:.1f}x" if d.get('current') else "--",
                    f"{d['low']:.1f}x" if d.get('low') else "--",
                    f"{d['high']:.1f}x" if d.get('high') else "--",
                    pct_str,
                ))
            tv.pack(fill=tk.X, pady=10)

            interp = ttk.LabelFrame(self._relval_frame, text="Interpretation", padding=8)
            interp.pack(fill=tk.X, pady=(6, 0))
            ttk.Label(interp, text=(
                "Percentile rank compares the current multiple to its own trailing 3-year range. "
                "0% = cheapest it has been in 3 years; 100% = most expensive. "
                "A low percentile (e.g. <20%) may indicate a value opportunity; "
                "a high percentile (>80%) suggests the stock is expensive relative to history. "
                "\u2022 P/E measures price vs earnings \u2022 P/B measures price vs book value "
                "\u2022 P/S measures price vs sales \u2022 EV/EBITDA measures enterprise value vs operating profit."
            ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Monte Carlo Tab ──
    def _build_monte_carlo_tab(self, parent):
        self._mc_frame = ttk.Frame(parent)
        self._mc_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ctrl = ttk.Frame(self._mc_frame)
        ctrl.pack(fill=tk.X)
        ttk.Label(ctrl, text="Iterations:").pack(side=tk.LEFT)
        self._mc_iter_var = tk.IntVar(value=10000)
        ttk.Spinbox(ctrl, from_=1000, to=50000, increment=1000,
                    textvariable=self._mc_iter_var, width=8).pack(side=tk.LEFT, padx=4)
        self._mc_run_btn = ttk.Button(ctrl, text="Run", command=self._run_mc)
        self._mc_run_btn.pack(side=tk.LEFT, padx=10)
        self._mc_results_frame = ttk.Frame(self._mc_frame)
        self._mc_results_frame.pack(fill=tk.BOTH, expand=True, pady=8)

    def _run_mc(self):
        for w in self._mc_results_frame.winfo_children():
            w.destroy()
        result, data = self._last_result, self._last_data
        if not result:
            ttk.Label(self._mc_results_frame, text="Run DCF first").pack(pady=20)
            return

        data['_estimated_growth'] = result.get('estimated_growth', result['growth_rate'])
        data['_wacc'] = result['wacc']

        status = ttk.Label(self._mc_results_frame, text="Running ...")
        status.pack(pady=20)

        def run():
            try:
                from monte_carlo import run_monte_carlo
                n = self._mc_iter_var.get()
                vals = run_monte_carlo(data, iterations=n)
                self.root.after(0, _display, vals, n)
            except Exception as e:
                self.root.after(0, lambda: status.config(text=f"Error: {e}"))

        def _display(vals, n):
            status.destroy()
            if not vals:
                ttk.Label(self._mc_results_frame, text="No valid results.").pack(pady=20)
                return
            arr = np.array(vals)
            price = data['price']

            import matplotlib
            matplotlib.use('TkAgg')
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure

            fig = Figure(figsize=(6, 3), dpi=100)
            ax = fig.add_subplot(111)
            ax.hist(arr, bins=60, color='#4a8bc2', alpha=0.7, edgecolor='white')
            ax.axvline(price, color='red', linewidth=1.5, linestyle='--', label=f'Current: {fmt_currency(price)}')
            ax.axvline(np.mean(arr), color='green', linewidth=1.2, linestyle='-', label=f'Mean: {fmt_currency(np.mean(arr))}')
            ax.axvline(np.median(arr), color='orange', linewidth=1.2, linestyle=':', label=f'Median: {fmt_currency(np.median(arr))}')
            ax.legend(fontsize=8)
            ax.set_title(f'Monte Carlo Distribution ({n:,} iterations)', fontsize=10)
            ax.set_xlabel('Intrinsic Value', fontsize=9)
            ax.set_ylabel('Frequency', fontsize=9)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=self._mc_results_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            stats = ttk.LabelFrame(self._mc_results_frame, text="Statistics", padding=6)
            stats.pack(fill=tk.X, pady=4)
            _kv_row(stats, "Mean", fmt_currency(np.mean(arr)))
            _kv_row(stats, "Median", fmt_currency(np.median(arr)))
            _kv_row(stats, "Std Dev", fmt_currency(np.std(arr)))
            _kv_row(stats, "5th Percentile", fmt_currency(np.percentile(arr, 5)))
            _kv_row(stats, "95th Percentile", fmt_currency(np.percentile(arr, 95)))
            _kv_row(stats, "Current Price", fmt_currency(price))
            pct_below = np.sum(arr <= price) / len(arr)
            _kv_row(stats, "P(Value ≤ Price)", f"{pct_below:.1%}")

            interp = ttk.LabelFrame(self._mc_results_frame, text="Interpretation", padding=8)
            interp.pack(fill=tk.X, pady=(4, 0))
            ttk.Label(interp, text=(
                "The histogram shows the distribution of possible intrinsic values from thousands of randomized DCF runs. "
                "Spread (Std Dev) reflects uncertainty. If Mean > Median, the distribution is right-skewed "
                "(upside potential exceeds downside risk). P(Value \u2264 Price) is the probability the stock is "
                "overvalued at the current price \u2014 lower is better for finding undervalued opportunities."
            ), wraplength=900, font=("Segoe UI", 9), foreground="#555").pack(anchor=tk.W)

        threading.Thread(target=run, daemon=True).start()

    # ── Watchlist Tab ──
    def _build_watchlist_tab(self, parent):
        self._wl_frame = ttk.Frame(parent)
        self._wl_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ctrl = ttk.Frame(self._wl_frame)
        ctrl.pack(fill=tk.X)
        self._wl_entry = ttk.Entry(ctrl, width=15, font=("Segoe UI", 10))
        self._wl_entry.pack(side=tk.LEFT, padx=(0, 4))
        self._wl_entry.bind("<Return>", lambda e: self._wl_add())
        ttk.Button(ctrl, text="Add", command=self._wl_add).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="Remove", command=self._wl_remove).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="Refresh All", command=self._wl_refresh).pack(side=tk.LEFT, padx=10)

        cols = ("ticker", "price", "intrinsic", "upside", "rec", "status")
        self._wl_tree = ttk.Treeview(self._wl_frame, columns=cols, show="headings", height=12)
        for c in cols:
            self._wl_tree.heading(c, text=c.title())
        self._wl_tree.column("ticker", width=80)
        self._wl_tree.column("price", width=100, anchor=tk.E)
        self._wl_tree.column("intrinsic", width=110, anchor=tk.E)
        self._wl_tree.column("upside", width=90, anchor=tk.E)
        self._wl_tree.column("rec", width=100, anchor=tk.CENTER)
        self._wl_tree.column("status", width=120)
        self._wl_tree.pack(fill=tk.BOTH, expand=True, pady=6)

        self._wl_refresh()

        ttk.Label(self._wl_frame,
                  text="Tickers auto-append .NS (NSE). Refresh runs DCF sequentially for all tickers.",
                  font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W, pady=(4, 0))

    def _wl_add(self):
        ticker = self._wl_entry.get().strip().upper()
        if "." not in ticker:
            ticker = ticker + ".NS"
        if ticker:
            self.portfolio.add(ticker)
            self._wl_entry.delete(0, tk.END)
            self._wl_refresh()

    def _wl_remove(self):
        sel = self._wl_tree.selection()
        if sel:
            ticker = self._wl_tree.item(sel[0], "values")[0]
            self.portfolio.remove(ticker)
            self._wl_refresh()

    def _wl_refresh(self):
        for item in self._wl_tree.get_children():
            self._wl_tree.delete(item)
        for ticker in self.portfolio.tickers():
            self._wl_tree.insert("", tk.END, values=(ticker, "--", "--", "--", "--", "queued"))

        def run():
            for i, ticker in enumerate(self.portfolio.tickers()):
                self.root.after(0, lambda t=ticker: self._wl_update_row(t, "fetching ..."))
                try:
                    fcfs = get_financials(ticker)
                    mkt = get_market_data(ticker)
                    bs = get_balance_sheet(ticker)
                    data = {
                        'historical_fcfs': fcfs,
                        'projection_years': 5,
                        'price': mkt['price'],
                        'shares_outstanding': mkt['shares_outstanding'],
                        'beta': mkt['beta'],
                        'market_cap': mkt['market_cap'],
                        'total_debt': bs['total_debt'],
                        'cash': bs['cash'],
                        'tax_rate': get_tax_rate(ticker),
                        'rf_rate': get_risk_free_rate(),
                        'terminal_growth_rate': 0.04,
                    }
                    r = run_dcf(data, market_premium=0.07)
                    rec = analyze(r, data)
                    up = r['upside']
                    self.root.after(0, lambda t=ticker, p=mkt['price'], iv=r['intrinsic_value'],
                                    u=up, a=rec['action']: self._wl_update_row(
                                        t, fmt_currency(p), fmt_currency(iv),
                                        f"{u:+.1%}" if u else "--", a, "done"))
                except Exception as e:
                    self.root.after(0, lambda t=ticker: self._wl_update_row(
                        t, "--", "--", "--", "--", f"error: {str(e)[:30]}"))

        threading.Thread(target=run, daemon=True).start()

    def _wl_update_row(self, ticker, *vals):
        items = self._wl_tree.get_children()
        for item in items:
            if self._wl_tree.item(item, "values")[0] == ticker:
                self._wl_tree.item(item, values=(ticker, *vals))
                break

    # ── Export Tab ──
    def _build_export_tab(self, parent):
        self._export_frame = ttk.Frame(parent)
        self._export_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(self._export_frame, text="Export DCF Report",
                  font=("Segoe UI", 14, "bold")).pack(anchor=tk.W, pady=(0, 10))

        opts = ttk.LabelFrame(self._export_frame, text="Include", padding=8)
        opts.pack(fill=tk.X)
        self._export_include = {}
        for sec in ['Valuation Summary', 'Recommendation', 'Cash Flow Table']:
            v = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(opts, text=sec, variable=v)
            cb.pack(anchor=tk.W, pady=1)
            self._export_include[sec] = v

        ttk.Label(self._export_frame, text="").pack()
        ttk.Button(self._export_frame, text="Export to CSV ...",
                   command=self._do_export).pack(anchor=tk.W)

        ttk.Label(self._export_frame,
                  text="Exports a CSV report with the selected sections. Only CSV format is supported.",
                  font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W, pady=(6, 0))

    def _do_export(self):
        if not self._last_result:
            messagebox.showwarning("No Data", "Run DCF first.")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".csv",
                                           filetypes=[("CSV files", "*.csv")])
        if not fp:
            return
        try:
            export_csv(fp, self._last_result, self._last_data,
                       rec=analyze(self._last_result, self._last_data))
            self.status_var.set(f"Exported to {fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ── Core DCF Flow ──
    def _resolve_ticker(self, ticker):
        if "." not in ticker:
            ticker = ticker + ".NS"
        return ticker

    def calculate(self):
        ticker = self.ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a ticker symbol.")
            return
        ticker = self._resolve_ticker(ticker)
        self.calc_btn.config(state=tk.DISABLED)
        self.research_btn.config(state=tk.DISABLED)
        self.status_var.set(f"Fetching data for {ticker} ...")
        threading.Thread(target=self._run, args=(ticker,), daemon=True).start()

    def _run(self, ticker):
        try:
            if ticker in self._fetched_data:
                data = self._fetched_data[ticker]
            else:
                fcfs = get_financials(ticker)
                mkt = get_market_data(ticker)
                bs = get_balance_sheet(ticker)
                tax_rate = get_tax_rate(ticker)
                rf_rate = get_risk_free_rate()
                data = {
                    'historical_fcfs': fcfs,
                    'price': mkt['price'],
                    'shares_outstanding': mkt['shares_outstanding'],
                    'beta': mkt['beta'],
                    'market_cap': mkt['market_cap'],
                    'total_debt': bs['total_debt'],
                    'cash': bs['cash'],
                    'tax_rate': tax_rate,
                    'rf_rate': rf_rate,
                }
                self._fetched_data[ticker] = data

            data['projection_years'] = self.years_var.get()
            try:
                term_g = float(self.term_g_var.get()) / 100
            except ValueError:
                term_g = 0.04
            data['terminal_growth_rate'] = term_g

            wacc_override = None
            raw = self.wacc_var.get().strip()
            if raw.lower() != "auto":
                try:
                    wacc_override = float(raw) / 100
                except ValueError:
                    pass

            result = run_dcf(data, wacc_override, market_premium=0.07)
            self._last_result = result
            self._last_data = data
            self._last_ticker = ticker

            self.root.after(0, self._update_ui, result, fcfs, data)

        except Exception as e:
            self.root.after(0, self._show_error, str(e))

    def _update_ui(self, result, hist_fcfs, data):
        sym = self.currency_sym
        self._result_labels["intrinsic"].config(text=fmt_currency(result['intrinsic_value'], sym))
        self._result_labels["price"].config(text=fmt_currency(result['current_price'], sym))

        upside = result.get('upside')
        if upside is not None:
            self._result_labels["upside"].config(text=f"{upside:+.1%}",
                                                 foreground="green" if upside > 0 else "red")
        else:
            self._result_labels["upside"].config(text="--", foreground="black")

        self._result_labels["growth_rate"].config(text=fmt_pct(result['growth_rate']))
        self._result_labels["wacc"].config(text=fmt_pct(result['wacc']))
        self._result_labels["terminal_value"].config(text=fmt_currency(result['terminal_value'], sym))
        self._result_labels["enterprise_value"].config(text=fmt_currency(result['enterprise_value'], sym))
        self._result_labels["equity_value"].config(text=fmt_currency(result['equity_value'], sym))

        if self.wacc_var.get().strip().lower() == "auto":
            self.wacc_var.set(f"{result['wacc'] * 100:.1f}")

        rec = analyze(result, data)
        action = rec['action']
        confidence = rec['confidence']
        bg = '#2d7d46' if action == 'BUY' else '#c0392b' if action == 'SHORT' else '#6b6b6b'
        self._rec_frame.config(bg=bg)
        self._rec_frame.grid()
        self._rec_frame.tkraise()
        self._rec_action.config(text=f"{action}  \u2014  {confidence} CONFIDENCE", bg=bg, fg="white")
        self._rec_summary.config(text=rec['summary'], bg=bg, fg="#e8e8e8")
        reasons_text = "\n".join(f"\u2022 {r}" for r in rec['reasons'])
        self._rec_reasons.config(text=reasons_text, bg=bg, fg="#cccccc")

        for item in self.tree.get_children():
            self.tree.delete(item)
        for dt, fcf in hist_fcfs:
            self.tree.insert("", tk.END, values=(str(dt.year), fmt_currency(fcf, sym), ""))
        last_yr = hist_fcfs[-1][0].year
        for i, fcf in enumerate(result['projected_fcfs'], 1):
            self.tree.insert("", tk.END, values=(str(last_yr + i), "", fmt_currency(fcf, sym)))

        self.calc_btn.config(state=tk.NORMAL)
        self.research_btn.config(state=tk.NORMAL)
        self.status_var.set("Done")

    def _show_error(self, msg):
        messagebox.showerror("Error", msg)
        self._rec_frame.grid_remove()
        self.calc_btn.config(state=tk.NORMAL)
        self.research_btn.config(state=tk.DISABLED)
        self.status_var.set("Error")

    # ── Research Window ──
    def _open_research(self):
        ticker = self._last_ticker
        if not ticker:
            return

        win = tk.Toplevel(self.root)
        win.title(f"Research Report \u2014 {ticker}")
        win.geometry("780x620")
        win.minsize(650, 450)

        top = ttk.Frame(win, padding="8")
        top.pack(fill=tk.X)
        ttk.Label(top, text="View:").pack(side=tk.LEFT, padx=(0, 5))
        view_var = tk.StringVar(value="Summary")
        view_cb = ttk.Combobox(top, textvariable=view_var,
                                values=["Summary", "Comprehensive"],
                                state="readonly", width=16)
        view_cb.pack(side=tk.LEFT)

        canvas = tk.Canvas(win, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        _bind_mousewheel(canvas)

        status_lbl = ttk.Label(scroll_frame, text="Loading ...", font=("Segoe UI", 11))
        status_lbl.pack(pady=30)

        def _rebuild():
            for w in scroll_frame.winfo_children():
                w.destroy()

        def _apply_view(mode):
            for child in scroll_frame.winfo_children():
                if hasattr(child, "_section"):
                    if mode == "Summary" and child._section == "comprehensive":
                        child.pack_forget()
                    elif mode == "Comprehensive" and child._section == "comprehensive":
                        child.pack(fill=tk.X, padx=10, pady=(0, 8))
                    elif mode == "Summary" and child._section == "summary":
                        child.pack(fill=tk.X, padx=10, pady=(10, 0))
                    elif mode == "Comprehensive" and child._section == "summary":
                        child.pack(fill=tk.X, padx=10, pady=(10, 0))

        view_cb.bind("<<ComboboxSelected>>", lambda e: _apply_view(view_var.get()))

        def _populate(report):
            _rebuild()
            from research_ui import build_summary, build_comprehensive
            build_summary(scroll_frame, report)
            build_comprehensive(scroll_frame, report)
            _apply_view(view_var.get())

        def fetch():
            try:
                report = generate_report(ticker)
                self.root.after(0, _populate, report)
            except Exception as e:
                self.root.after(0, lambda: (_rebuild(),
                    ttk.Label(scroll_frame, text=f"Error: {e}").pack(pady=30)))

        threading.Thread(target=fetch, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = DCFApp(root)
    root.mainloop()
