import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker


def build_fcf_chart(parent_frame, hist_fcfs, projected_fcfs, wacc, currency_sym="Rs"):
    fig = Figure(figsize=(6, 3.5), dpi=100)
    ax = fig.add_subplot(111)

    years_h = [dt.year for dt, _ in hist_fcfs]
    vals_h = [f for _, f in hist_fcfs]

    last_yr = years_h[-1]
    years_p = [last_yr + i for i in range(1, len(projected_fcfs) + 1)]

    bars_h = ax.bar(years_h, [v / 1e7 for v in vals_h],
                    color='#4a8bc2', alpha=0.75, label='Historical FCF', width=0.6)
    bars_p = ax.bar(years_p, [v / 1e7 for v in projected_fcfs],
                    color='#2d7d46', alpha=0.75, label='Projected FCF', width=0.6)

    pv = [projected_fcfs[i] / (1 + wacc) ** (i + 1) for i in range(len(projected_fcfs))]
    ax.plot(years_p, [v / 1e7 for v in pv], 'r--', linewidth=1.5,
            label='PV of Projected', marker='o', markersize=3)

    ax.axhline(y=0, color='gray', linewidth=0.5)
    ax.set_ylabel('Value (Cr)', fontsize=9)
    ax.set_title('Free Cash Flow Projection', fontsize=10, fontweight='bold')
    ax.legend(fontsize=8, loc='upper left')
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f'))

    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=parent_frame)
    canvas.draw()

    return canvas.get_tk_widget()
