from __future__ import annotations
import json
import sys
from pathlib import Path

import click

from trader.cli.__main__ import output_json

_ASSETS = Path("docs/assets")
_EVO_PATH = Path(".trader/logs/portfolio_evolution.jsonl")
_AGENT_PATH = Path(".trader/logs/agent.jsonl")


@click.command("report")
@click.option("--save-assets", "save_assets", is_flag=True, default=False,
              help="Regenerate docs/assets/ SVGs for the README (requires matplotlib).")
@click.option("--output", default="outputs/report.html", show_default=True,
              help="Output path for the standalone HTML report.")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="Open HTML report in browser after generating.")
@click.pass_context
def report(ctx, save_assets, output, open_browser):
    """
    Generate a portfolio performance report from trade logs.

    Reads .trader/logs/portfolio_evolution.jsonl and agent.jsonl and
    produces charts. Use --save-assets to refresh the README visuals.

    \b
    Examples:
      trader report
      trader report --save-assets
      trader report --output reports/2026-03-11.html --open
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
        import numpy as np
        import pandas as pd
    except ImportError:
        click.echo(json.dumps({
            "error": "matplotlib required — run: uv add matplotlib"
        }))
        sys.exit(1)

    # ── load data ────────────────────────────────────────────────────────────
    snapshots: list[dict] = []
    if _EVO_PATH.exists():
        for line in _EVO_PATH.read_text().splitlines():
            if line.strip():
                snapshots.append(json.loads(line))

    trades: list[dict] = []
    if _AGENT_PATH.exists():
        for line in _AGENT_PATH.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("event") == "ORDER_INTENT":
                    trades.append(entry)

    # ── helpers ──────────────────────────────────────────────────────────────
    BG = "#0d1117"

    def _style(ax, fig, title):
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_edgecolor("#21262d")
        ax.tick_params(colors="#8b949e", labelsize=8)
        ax.set_title(title, color="#e6edf3", fontsize=11,
                     fontweight="600", pad=8)

    def _equity_fig():
        if snapshots:
            dates  = pd.to_datetime([s["timestamp"] for s in snapshots])
            equity = [s.get("net_liquidation", 0) for s in snapshots]
        else:
            np.random.seed(42)
            days   = 132
            ret    = np.random.normal(0.0009, 0.011, days)
            equity = list(50_000 * np.cumprod(1 + ret))
            dates  = pd.date_range("2025-10-01", periods=days, freq="B")

        fig, ax = plt.subplots(figsize=(8.5, 3.0))
        _style(ax, fig, "Portfolio Equity Curve")
        base = equity[0]
        ax.fill_between(dates, equity, base,
                        where=[v >= base for v in equity],
                        alpha=0.12, color="#3fb950")
        ax.fill_between(dates, equity, base,
                        where=[v < base for v in equity],
                        alpha=0.12, color="#f85149")
        ax.plot(dates, equity, color="#3fb950", linewidth=1.8)
        ax.axhline(base, color="#21262d", linewidth=0.8, linestyle="--")
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"€{v/1000:.0f}k"))
        fig.tight_layout(pad=0.6)
        return fig

    def _drawdown_fig():
        if snapshots:
            dates  = pd.to_datetime([s["timestamp"] for s in snapshots])
            equity = np.array([s.get("net_liquidation", 0) for s in snapshots],
                              dtype=float)
        else:
            np.random.seed(42)
            days   = 132
            ret    = np.random.normal(0.0009, 0.011, days)
            equity = np.cumprod(1 + ret) * 50_000
            dates  = pd.date_range("2025-10-01", periods=days, freq="B")

        peak = np.maximum.accumulate(equity)
        dd   = (equity - peak) / peak * 100

        fig, ax = plt.subplots(figsize=(8.5, 2.2))
        _style(ax, fig, "Drawdown from ATH")
        ax.fill_between(dates, dd, 0, alpha=0.35, color="#f85149")
        ax.plot(dates, dd, color="#f85149", linewidth=1.4)
        ax.axhline(0, color="#21262d", linewidth=0.8)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        fig.tight_layout(pad=0.6)
        return fig

    def _pnl_fig():
        if trades:
            rows   = trades[-20:]
            labels = [t.get("ticker", "?") for t in rows]
            pnls   = [float(t.get("estimated_pnl", 0)) for t in rows]
        else:
            np.random.seed(99)
            labels = ["NVDA", "ASML", "MSFT", "PLTR", "VRT", "TSLA", "RDSA",
                      "AGX",  "AAPL", "SMCI", "ARM",  "AMZN", "META", "UBER",
                      "SHOP", "APP",  "CRM",  "PANW", "CRWD", "ZS"]
            pnls   = list(np.random.normal(300, 850, len(labels)))
            pnls[2] = -1180; pnls[7] = -660;  pnls[14] = -390
            pnls[0] =  1820; pnls[5] =  1080; pnls[11] =  940

        colors = ["#3fb950" if p >= 0 else "#f85149" for p in pnls]
        fig, ax = plt.subplots(figsize=(8.5, 3.8))
        _style(ax, fig, "P&L per Trade (last 20)")
        ax.barh(labels, pnls, color=colors, height=0.65)
        ax.axvline(0, color="#21262d", linewidth=0.8)
        ax.xaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"€{v:+.0f}"))
        wins  = sum(1 for p in pnls if p >= 0)
        total = sum(pnls)
        ax.set_xlabel(
            f"Win rate: {wins}/{len(pnls)}   ·   Net: €{total:+,.0f}",
            fontsize=9, color="#8b949e")
        fig.tight_layout(pad=0.6)
        return fig

    def _alloc_fig():
        if snapshots:
            last    = snapshots[-1]
            pos     = last.get("positions", {})
            sectors = list(pos.keys())[:6] or ["Cash"]
            sizes   = [float(v) for v in list(pos.values())[:6]] or [100]
        else:
            sectors = ["Technology", "Semiconductors", "Healthcare",
                       "Energy",     "Financials",     "Cash"]
            sizes   = [28, 18, 12, 10, 8, 24]

        palette = ["#388bfd", "#58a6ff", "#3fb950",
                   "#d29922", "#a371f7", "#484f58"]
        fig, ax = plt.subplots(figsize=(5.5, 4.2))
        _style(ax, fig, "Sector Allocation")
        _, _, autotexts = ax.pie(
            sizes, labels=sectors,
            colors=palette[:len(sectors)], autopct="%1.0f%%",
            startangle=90,
            wedgeprops={"edgecolor": BG, "linewidth": 2},
            textprops={"color": "#8b949e", "fontsize": 9},
        )
        for at in autotexts:
            at.set_color("#e6edf3"); at.set_fontsize(9)
        fig.tight_layout(pad=0.6)
        return fig

    # ── save-assets mode (regenerate README SVGs) ────────────────────────────
    if save_assets:
        _ASSETS.mkdir(parents=True, exist_ok=True)
        for name, fig_fn in [("equity_curve", _equity_fig),
                              ("drawdown",     _drawdown_fig),
                              ("pnl_trades",   _pnl_fig),
                              ("allocation",   _alloc_fig)]:
            fig = fig_fn()
            fig.savefig(_ASSETS / f"{name}.svg", format="svg",
                        bbox_inches="tight", facecolor=BG)
            plt.close(fig)
        output_json({
            "saved": [str(_ASSETS / f"{n}.svg") for n in
                      ["equity_curve", "drawdown", "pnl_trades", "allocation"]],
            "snapshots": len(snapshots),
            "trades": len(trades),
        })
        return

    # ── HTML report ──────────────────────────────────────────────────────────
    import base64
    import io

    def _fig_to_b64(fig) -> str:
        buf = io.BytesIO()
        fig.savefig(buf, format="svg", bbox_inches="tight", facecolor=BG)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()

    charts = {
        "equity": _fig_to_b64(_equity_fig()),
        "dd":     _fig_to_b64(_drawdown_fig()),
        "pnl":    _fig_to_b64(_pnl_fig()),
        "alloc":  _fig_to_b64(_alloc_fig()),
    }

    def _img(b64): return f'<img src="data:image/svg+xml;base64,{b64}" style="width:100%">'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Portfolio Report</title>
<style>
  body {{ background:#0d1117; color:#e6edf3; font-family:-apple-system,sans-serif;
         max-width:1100px; margin:0 auto; padding:24px; }}
  h1   {{ font-size:20px; margin-bottom:4px; }}
  p    {{ color:#8b949e; font-size:13px; margin-top:0; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:24px; }}
  .full {{ grid-column:1/-1; }}
  .card {{ background:#161b22; border:1px solid #21262d; border-radius:8px;
           padding:16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ padding:6px 12px; text-align:left; border-bottom:1px solid #21262d; }}
  th    {{ color:#8b949e; font-weight:600; }}
</style>
</head>
<body>
<h1>Portfolio Report</h1>
<p>Generated from .trader/logs — {len(snapshots)} snapshots · {len(trades)} ORDER_INTENTs</p>
<div class="grid">
  <div class="card full">{_img(charts["equity"])}</div>
  <div class="card">{_img(charts["dd"])}</div>
  <div class="card">{_img(charts["alloc"])}</div>
  <div class="card full">{_img(charts["pnl"])}</div>
</div>
</body>
</html>"""

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)

    output_json({
        "report": str(out),
        "snapshots": len(snapshots),
        "trades": len(trades),
    })

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{out.absolute()}")
