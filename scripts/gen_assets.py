#!/usr/bin/env python3
"""Generate README visual assets: workflow diagram + demo portfolio charts.

Usage:
    uv run python scripts/gen_assets.py
"""

from pathlib import Path

ASSETS = Path("docs/assets")
ASSETS.mkdir(parents=True, exist_ok=True)

# ── colour palette (GitHub dark) ─────────────────────────────────────────────
C = {
    "bg":        "#0d1117",
    "box":       "#161b22",
    "border":    "#21262d",
    "blue_bg":   "#0c1c33",  "blue":   "#388bfd",
    "green_bg":  "#0d2818",  "green":  "#3fb950",
    "orange_bg": "#221a00",  "orange": "#d29922",
    "red_bg":    "#280d0d",  "red":    "#f85149",
    "purple_bg": "#160d22",  "purple": "#a371f7",
    "text":      "#e6edf3",
    "gray":      "#8b949e",
}


# ── SVG primitives ────────────────────────────────────────────────────────────
def _rect(x, y, w, h, rx=7, fill=None, stroke=None, sw=1.2, dash=""):
    fill   = fill   or C["box"]
    stroke = stroke or C["border"]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def _text(x, y, t, size=11, fill=None, anchor="middle", weight="normal"):
    fill = fill or C["text"]
    t = str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}" '
            f'font-size="{size}" font-weight="{weight}">{t}</text>')


def _line(x1, y1, x2, y2, stroke=None, sw=1.5, dash="", marker=""):
    stroke = stroke or C["border"]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}{m}/>')


def _path(d, stroke=None, sw=1.5, fill="none", dash="", marker=""):
    stroke = stroke or C["border"]
    da = f' stroke-dasharray="{dash}"' if dash else ""
    ma = f' marker-end="url(#{marker})"' if marker else ""
    return (f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" '
            f'fill="{fill}"{da}{ma}/>')


# ── Workflow diagram ──────────────────────────────────────────────────────────
def workflow_svg() -> str:
    W, H = 900, 720
    els = []
    els.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        'style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\','
        'Helvetica,Arial,sans-serif">'
    )

    def _marker(mid, color):
        return (f'<marker id="{mid}" markerWidth="10" markerHeight="7" '
                f'refX="9" refY="3.5" orient="auto">'
                f'<polygon points="0 0,10 3.5,0 7" fill="{color}"/></marker>')

    els.append("<defs>")
    for mid, col in [("a", C["gray"]), ("ag", C["green"]),
                     ("ar", C["red"]),  ("ap", C["purple"])]:
        els.append(_marker(mid, col))
    els.append("</defs>")

    # background
    els.append(_rect(0, 0, W, H, rx=12, fill=C["bg"], stroke=C["bg"], sw=0))

    # title
    els.append(_text(W // 2, 26, "Autonomous Portfolio Conductor",
                     size=14, weight="600"))
    els.append(_text(W // 2, 42, "Agentic Workflow · All Times CET",
                     size=10, fill=C["gray"]))

    # ── TRIGGER CHIPS ────────────────────────────────────────────────────────
    triggers = [
        ("EU Pre-market", "8:03am",  C["blue_bg"],   C["blue"]),
        ("EU Market",     "9am–3pm", C["blue_bg"],   C["blue"]),
        ("EU+US Overlap", "3:03pm",  C["orange_bg"], C["orange"]),
        ("US Market",     "5–9pm",   C["blue_bg"],   C["blue"]),
        ("Weekly",        "Sun 6pm", C["purple_bg"], C["purple"]),
        ("Monthly",       "1st Sun", C["purple_bg"], C["purple"]),
    ]
    cw, ch, chip_y = 126, 36, 58
    gap_c = (W - 6 * cw) // 7
    chip_lefts = [gap_c + i * (cw + gap_c) for i in range(6)]
    chip_cxs   = [x + cw // 2 for x in chip_lefts]

    for i, (lbl, sub, bg, brd) in enumerate(triggers):
        x = chip_lefts[i]
        els.append(_rect(x, chip_y, cw, ch, rx=6, fill=bg, stroke=brd, sw=1.5))
        els.append(_text(x + cw // 2, chip_y + 14, lbl, size=9, weight="500"))
        els.append(_text(x + cw // 2, chip_y + 27, sub, size=9, fill=C["gray"]))

    # fan-in bar → arrow to conductor
    bar_y    = chip_y + ch + 12          # 106
    cond_top = bar_y + 18                # 124
    for cx in chip_cxs:
        els.append(_line(cx, chip_y + ch, cx, bar_y, stroke=C["border"], sw=1.2))
    els.append(_line(chip_cxs[0], bar_y, chip_cxs[-1], bar_y,
                     stroke=C["border"], sw=1.2))
    els.append(_line(W // 2, bar_y, W // 2, cond_top - 2,
                     stroke=C["gray"], sw=1.5, marker="a"))

    # ── CONDUCTOR ────────────────────────────────────────────────────────────
    cond_w, cond_h = 260, 44
    cond_x   = W // 2 - cond_w // 2     # 320
    cond_y   = cond_top                  # 124
    cond_cx  = W // 2                    # 450
    cond_bot = cond_y + cond_h           # 168

    els.append(_rect(cond_x, cond_y, cond_w, cond_h, rx=8,
                     fill=C["orange_bg"], stroke=C["orange"], sw=2))
    els.append(_text(cond_cx, cond_y + 18, "Portfolio Conductor",
                     size=13, weight="600"))
    els.append(_text(cond_cx, cond_y + 33, "sole order-placement agent",
                     size=10, fill=C["gray"]))

    # ── MAIN STEPS ───────────────────────────────────────────────────────────
    step_x, step_w, step_h, s_gap = 250, 400, 40, 14
    step_cx = step_x + step_w // 2      # 450

    STEPS = [
        ("① Live Snapshot",
         "positions · cash · open orders  →  portfolio_evolution.jsonl",
         C["blue"], None),
        ("② Session Gates",
         "Calendar  →  risk_mode   ·   Geo Scan  →  geo_context",
         C["blue"], None),
        ("③ Market News Analyst",
         "held tickers + watchlist  →  news_context per ticker",
         C["blue"], None),
        ("④ Risk Monitor",
         "news + geo context  →  stop / trim proposals",
         C["blue"], None),
        ("⑤ Portfolio Health",
         "concentration · drift · HHI  →  rebalance proposals",
         C["blue"], None),
        ("⑥ Opportunity Finder",
         "EU stocks · US stocks · UCITS ETFs   [skipped if ELEVATED risk]",
         C["orange"], C["orange_bg"]),
        ("⑦ Order Alert Manager",
         "alert lifecycle · dedup · bracket entries  →  action list",
         C["blue"], None),
        ("⑧ Guardrails",
         "cash-only · position ≤5% NLV · cash ≥10% · ≤3 trades/day",
         C["orange"], C["orange_bg"]),
    ]

    # arrow from conductor to first step
    first_y = cond_bot + 26             # 194
    els.append(_line(cond_cx, cond_bot, cond_cx, first_y - 2,
                     stroke=C["gray"], sw=1.5, marker="a"))

    step_ys, cur_y = [], first_y
    for i, (title, sub, accent, bg_ov) in enumerate(STEPS):
        step_ys.append(cur_y)
        bg = bg_ov or C["box"]
        els.append(_rect(step_x, cur_y, step_w, step_h, rx=6,
                         fill=bg, stroke=C["border"], sw=1.2))
        els.append(_rect(step_x, cur_y, 4, step_h, rx=2,
                         fill=accent, stroke=accent, sw=0))
        els.append(_text(step_x + 14, cur_y + 15, title,
                         size=11, weight="600", anchor="start"))
        els.append(_text(step_x + 14, cur_y + 30, sub,
                         size=8.5, fill=C["gray"], anchor="start"))
        bot = cur_y + step_h
        cur_y += step_h + s_gap
        if i < len(STEPS) - 1:
            els.append(_line(step_cx, bot, step_cx, cur_y - 2,
                             stroke=C["gray"], sw=1.5, marker="a"))

    guard_y   = step_ys[-1]             # 572
    guard_bot = guard_y + step_h        # 612

    # ── OUTCOMES ─────────────────────────────────────────────────────────────
    out_y = guard_bot + 28              # 640

    # approved → execute
    exec_w, exec_h = 220, 40
    exec_x = step_cx - exec_w // 2
    els.append(_line(step_cx, guard_bot, step_cx, out_y - 2,
                     stroke=C["green"], sw=1.5, marker="ag"))
    els.append(_text(step_cx + 6, guard_bot + 14, "approved",
                     size=9, fill=C["green"], anchor="start"))
    els.append(_rect(exec_x, out_y, exec_w, exec_h, rx=6,
                     fill=C["green_bg"], stroke=C["green"], sw=1.5))
    els.append(_rect(exec_x, out_y, 4, exec_h, rx=2,
                     fill=C["green"], stroke=C["green"], sw=0))
    els.append(_text(step_cx, out_y + 16, "⑨ Execute",
                     size=12, weight="600"))
    els.append(_text(step_cx, out_y + 31, "trader orders buy / sell / stop",
                     size=9, fill=C["gray"]))

    # blocked → skip (left of steps, L-shaped path)
    skip_x, skip_w2, skip_h = 22, 156, 40
    skip_y   = out_y
    skip_mid = skip_y + skip_h // 2
    guard_mid = guard_y + step_h // 2

    els.append(_path(
        f"M {step_x} {guard_mid} L 190 {guard_mid} "
        f"L 190 {skip_mid} L {skip_x + skip_w2} {skip_mid}",
        stroke=C["red"], sw=1.5, dash="4,3", marker="ar"))
    els.append(_text(step_x - 4, guard_mid - 5, "blocked",
                     size=9, fill=C["red"], anchor="end"))
    els.append(_rect(skip_x, skip_y, skip_w2, skip_h, rx=6,
                     fill=C["red_bg"], stroke=C["red"], sw=1.2))
    els.append(_text(skip_x + skip_w2 // 2, skip_y + 15,
                     "✗ Log & Skip", size=10, fill=C["red"], weight="500"))
    els.append(_text(skip_x + skip_w2 // 2, skip_y + 29,
                     "CASH_FLOOR_BLOCK etc.", size=8.5, fill=C["gray"]))

    # ── PERIODIC REVIEWS (right column) ──────────────────────────────────────
    per_x = step_x + step_w + 22        # 672
    per_w = W - per_x - 14              # 214
    per_cx = per_x + per_w // 2

    # weekly
    wk_y, wk_h = first_y, 118
    els.append(_rect(per_x, wk_y, per_w, wk_h, rx=6,
                     fill=C["purple_bg"], stroke=C["purple"], sw=1.2, dash="5,3"))
    els.append(_text(per_cx, wk_y + 15, "Weekly · Sun 6pm",
                     size=9.5, fill=C["purple"], weight="600"))
    for j, itm in enumerate(["Market Top Detector", "Sector Analyst",
                              "Market News Analyst", "Strategy Optimizer",
                              "Performance Review"]):
        els.append(_text(per_x + 10, wk_y + 30 + j * 17, f"· {itm}",
                         size=8.5, fill=C["gray"], anchor="start"))

    # monthly
    mo_y, mo_h = wk_y + wk_h + 12, 88
    els.append(_rect(per_x, mo_y, per_w, mo_h, rx=6,
                     fill=C["purple_bg"], stroke=C["purple"], sw=1.2, dash="5,3"))
    els.append(_text(per_cx, mo_y + 15, "Monthly · 1st Sun 6pm",
                     size=9.5, fill=C["purple"], weight="600"))
    for j, itm in enumerate(["Strategy Optimizer", "System Improver",
                              "Decision quality audit + self-improvement"]):
        els.append(_text(per_x + 10, mo_y + 28 + j * 20, f"· {itm}",
                         size=8.5, fill=C["gray"], anchor="start"))

    # conductor → periodic (dashed L-path)
    p_mid_y = wk_y + wk_h // 2
    els.append(_path(
        f"M {cond_x + cond_w} {cond_y + cond_h // 2} "
        f"L 630 {cond_y + cond_h // 2} "
        f"L 630 {p_mid_y} L {per_x} {p_mid_y}",
        stroke=C["purple"], sw=1.2, dash="4,3", marker="ap"))
    els.append(_text(cond_x + cond_w + 4, cond_y + cond_h // 2 - 5,
                     "weekly / monthly",
                     size=8, fill=C["purple"], anchor="start"))

    els.append("</svg>")
    return "\n".join(els)


# ── Portfolio charts (matplotlib) ─────────────────────────────────────────────
def _setup_ax(ax, fig, title):
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    for spine in ax.spines.values():
        spine.set_edgecolor(C["border"])
    ax.tick_params(colors=C["gray"], labelsize=8)
    ax.set_title(title, color=C["text"], fontsize=11, fontweight="600", pad=8)
    ax.xaxis.label.set_color(C["gray"])
    ax.yaxis.label.set_color(C["gray"])


def equity_curve_svg():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    import pandas as pd

    np.random.seed(42)
    days = 132
    ret = np.random.normal(0.0009, 0.011, days)
    ret[:40]  *= 0.6
    ret[40:90] *= 1.4
    ret[90:]   *= 0.9
    equity = 50_000 * np.cumprod(1 + ret)
    dates  = pd.date_range("2025-10-01", periods=days, freq="B")

    fig, ax = plt.subplots(figsize=(8.5, 3.0))
    _setup_ax(ax, fig, "Portfolio Equity Curve")

    ax.fill_between(dates, equity, equity[0],
                    where=(equity >= equity[0]), alpha=0.12, color=C["green"])
    ax.fill_between(dates, equity, equity[0],
                    where=(equity < equity[0]),  alpha=0.12, color=C["red"])
    ax.plot(dates, equity, color=C["green"], linewidth=1.8, zorder=3)
    ax.axhline(equity[0], color=C["border"], linewidth=0.8, linestyle="--")

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"€{v/1000:.0f}k"))
    fig.tight_layout(pad=0.6)
    fig.savefig(ASSETS / "equity_curve.svg", format="svg",
                bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print("✓ equity_curve.svg")


def drawdown_svg():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    import pandas as pd

    np.random.seed(42)
    days = 132
    ret    = np.random.normal(0.0009, 0.011, days)
    equity = np.cumprod(1 + ret)
    peak   = np.maximum.accumulate(equity)
    dd     = (equity - peak) / peak * 100
    dates  = pd.date_range("2025-10-01", periods=days, freq="B")

    fig, ax = plt.subplots(figsize=(8.5, 2.2))
    _setup_ax(ax, fig, "Drawdown from ATH")

    ax.fill_between(dates, dd, 0, alpha=0.35, color=C["red"])
    ax.plot(dates, dd, color=C["red"], linewidth=1.4)
    ax.axhline(0, color=C["border"], linewidth=0.8)

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    fig.tight_layout(pad=0.6)
    fig.savefig(ASSETS / "drawdown.svg", format="svg",
                bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print("✓ drawdown.svg")


def pnl_trades_svg():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    np.random.seed(99)
    tickers = ["NVDA", "ASML", "MSFT", "PLTR", "VRT", "TSLA", "RDSA",
               "AGX",  "AAPL", "SMCI", "ARM",  "AMZN", "META", "UBER",
               "SHOP", "APP",  "CRM",  "PANW", "CRWD", "ZS"]
    pnls = np.random.normal(300, 850, len(tickers))
    # sprinkle some realism
    pnls[2]  = -1180;  pnls[7]  = -660;  pnls[14] = -390
    pnls[0]  =  1820;  pnls[5]  =  1080; pnls[11] =  940
    colors   = [C["green"] if p >= 0 else C["red"] for p in pnls]

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    _setup_ax(ax, fig, "P&L per Trade (last 20)")

    ax.barh(tickers, pnls, color=colors, height=0.65, zorder=3)
    ax.axvline(0, color=C["border"], linewidth=0.8)
    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"€{v:+.0f}"))

    wins  = sum(1 for p in pnls if p >= 0)
    total = sum(pnls)
    ax.set_xlabel(f"Win rate: {wins}/{len(pnls)}   ·   Net: €{total:+,.0f}",
                  fontsize=9)
    fig.tight_layout(pad=0.6)
    fig.savefig(ASSETS / "pnl_trades.svg", format="svg",
                bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print("✓ pnl_trades.svg")


def allocation_svg():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sectors = ["Technology", "Semiconductors", "Healthcare",
               "Energy",     "Financials",     "Cash"]
    sizes   = [28, 18, 12, 10, 8, 24]
    colors  = [C["blue"], "#58a6ff", C["green"],
               C["orange"], C["purple"], C["border"]]

    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    _setup_ax(ax, fig, "Sector Allocation")

    wedges, texts, autotexts = ax.pie(
        sizes, labels=sectors, colors=colors, autopct="%1.0f%%",
        startangle=90,
        wedgeprops={"edgecolor": C["bg"], "linewidth": 2},
        textprops={"color": C["gray"], "fontsize": 9},
    )
    for at in autotexts:
        at.set_color(C["text"])
        at.set_fontsize(9)

    fig.tight_layout(pad=0.6)
    fig.savefig(ASSETS / "allocation.svg", format="svg",
                bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    print("✓ allocation.svg")


# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    (ASSETS / "workflow.svg").write_text(workflow_svg())
    print("✓ workflow.svg")

    equity_curve_svg()
    drawdown_svg()
    pnl_trades_svg()
    allocation_svg()

    print(f"\nAll assets written to {ASSETS}/")
