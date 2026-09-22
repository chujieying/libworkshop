#!/usr/bin/env python3
"""Build a self-contained index.html from data/wvs-synthetic.csv.

Standard library only. Deterministic: SEED is fixed and rows are sorted before
sampling, so running this script twice produces a byte-identical index.html.

    python generate_index.py

The generated page embeds every computed result inline. It never reads the CSV
at runtime, makes no network requests, and needs no charting library, so it
works both by double-clicking it locally and when served by GitHub Pages.
"""

import csv
import html
import math
import random
from collections import Counter
from pathlib import Path

SEED = 42
HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "data" / "wvs-synthetic.csv"
OUT_PATH = HERE / "index.html"

ID_COLUMN = "respondent_id"          # identifier only: never charted or listed
SAMPLE_PER_COUNTRY = 300             # for the China vs India individual scatter
SCATTER_COUNTRIES = ("China", "India")
HEATMAP_COUNTRY = "Singapore"

# Country order is fixed so colours never shift between charts.
COUNTRIES = ["China", "India", "Kazakhstan", "Singapore", "Turkey"]

# Okabe-Ito, the reference colour-blind-safe qualitative palette.
COLORS = {
    "China": "#E69F00",       # gold
    "India": "#0072B2",       # blue
    "Kazakhstan": "#009E73",  # teal
    "Singapore": "#D55E00",   # red
    "Turkey": "#CC79A7",      # purple
}

# Colour is never the only channel: every country also owns a marker shape...
MARKERS = {
    "China": "circle",
    "India": "diamond",
    "Kazakhstan": "cross",
    "Singapore": "square",
    "Turkey": "triangle",
}

# ...and, on the radar, a dash pattern.
DASHES = {
    "China": "none",
    "India": "11 5",
    "Kazakhstan": "1 5",
    "Singapore": "7 4",
    "Turkey": "3 3",
}

SCALE_NOTES = {
    "country": "5 countries",
    "age": "years, 16-90",
    "urban_rural": "Urban / Rural",
    "income_level": "Low / Medium / High",
    "sex": "Female / Male",
    "marital_status": "6 levels",
    "education": "Lower / Middle / Higher",
    "life_satisfaction": "1 = dissatisfied, 10 = satisfied",
    "freedom_of_choice": "1 = no choice, 10 = a great deal",
    "emancipative_values": "index, 0-1",
    "trust_people": "Trusted / Not trusted",
    "importance_of_god": "1 = not at all, 10 = very",
    "financial_satisfaction": "1 = dissatisfied, 10 = satisfied",
    "secular_values": "index, 0-1",
}

RADAR_AXES = [
    ("Life satisfaction", "life_satisfaction", "scale10"),
    ("Trusts others", "trust_people", "share"),
    ("Importance of god", "importance_of_god", "scale10"),
    ("Emancipative values", "emancipative_values", "index"),
    ("Secular values", "secular_values", "index"),
    ("Financial satisfaction", "financial_satisfaction", "scale10"),
]


# --------------------------------------------------------------------------- #
# formatting: every number that reaches the screen goes through one of these
# --------------------------------------------------------------------------- #

def f_index(x):
    """0-1 indices and shares: 2 decimal places."""
    return f"{x:.2f}"


def f_scale(x):
    """1-10 means: 1 decimal place."""
    return f"{x:.1f}"


def f_pct(x):
    """A 0-1 proportion as a whole percent."""
    return f"{round(x * 100)}%"


def f_int(n):
    return f"{n:,}"


def esc(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------- #
# load, profile, clean
# --------------------------------------------------------------------------- #

def load_rows():
    # utf-8-sig drops the byte-order mark this file starts with.
    with CSV_PATH.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = [c.strip() for c in reader.fieldnames]
        rows = []
        for raw in reader:
            rows.append({c: (raw[c] or "").strip() for c in columns})
    return columns, rows


def infer_type(column, values):
    """Human-readable data type, inferred from the non-blank values."""
    if not values:
        return "empty"
    try:
        nums = [float(v) for v in values]
    except ValueError:
        return "categorical (text)"
    if all(float(n).is_integer() for n in nums):
        lo, hi = int(min(nums)), int(max(nums))
        if (lo, hi) == (1, 10):
            return "ordinal integer (1-10)"
        return f"integer ({lo}-{hi})"
    return "continuous (0-1)"


def profile(columns, rows):
    out = []
    for col in columns:
        if col == ID_COLUMN:
            continue
        values = [r[col] for r in rows if r[col] != ""]
        out.append({
            "name": col,
            "dtype": infer_type(col, values),
            "n": len(values),
            "missing": len(rows) - len(values),
            "note": SCALE_NOTES.get(col, ""),
        })
    return out


def mean(xs):
    return sum(xs) / len(xs)


# --------------------------------------------------------------------------- #
# tiny SVG helpers
# --------------------------------------------------------------------------- #

def marker(shape, cx, cy, size, fill, stroke="none", stroke_width=0, title=None,
           opacity=None):
    """One data marker. `size` is the radius-ish half-extent in user units."""
    s = size
    attrs = (f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"'
             f'{f" opacity={chr(34)}{opacity}{chr(34)}" if opacity else ""}')
    if shape == "circle":
        body = f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{s:.2f}" {attrs}/>'
    elif shape == "square":
        body = (f'<rect x="{cx - s * 0.9:.2f}" y="{cy - s * 0.9:.2f}" '
                f'width="{s * 1.8:.2f}" height="{s * 1.8:.2f}" {attrs}/>')
    elif shape == "triangle":
        pts = (f"{cx:.2f},{cy - s * 1.15:.2f} "
               f"{cx + s * 1.05:.2f},{cy + s * 0.75:.2f} "
               f"{cx - s * 1.05:.2f},{cy + s * 0.75:.2f}")
        body = f'<polygon points="{pts}" {attrs}/>'
    elif shape == "diamond":
        pts = (f"{cx:.2f},{cy - s * 1.25:.2f} {cx + s * 1.15:.2f},{cy:.2f} "
               f"{cx:.2f},{cy + s * 1.25:.2f} {cx - s * 1.15:.2f},{cy:.2f}")
        body = f'<polygon points="{pts}" {attrs}/>'
    elif shape == "cross":
        w = s * 0.62
        pts = (f"{cx - w:.2f},{cy - s * 1.25:.2f} {cx + w:.2f},{cy - s * 1.25:.2f} "
               f"{cx + w:.2f},{cy - w:.2f} {cx + s * 1.25:.2f},{cy - w:.2f} "
               f"{cx + s * 1.25:.2f},{cy + w:.2f} {cx + w:.2f},{cy + w:.2f} "
               f"{cx + w:.2f},{cy + s * 1.25:.2f} {cx - w:.2f},{cy + s * 1.25:.2f} "
               f"{cx - w:.2f},{cy + w:.2f} {cx - s * 1.25:.2f},{cy + w:.2f} "
               f"{cx - s * 1.25:.2f},{cy - w:.2f} {cx - w:.2f},{cy - w:.2f}")
        body = f'<polygon points="{pts}" {attrs}/>'
    else:
        raise ValueError(shape)
    if title:
        return f"<g><title>{esc(title)}</title>{body}</g>"
    return body


def nice_ticks(lo, hi, target=5):
    span = hi - lo
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        step = mag * mult
        if step >= raw:
            break
    start = math.ceil(lo / step - 1e-9) * step
    ticks, t = [], start
    while t <= hi + 1e-9:
        ticks.append(round(t, 10))
        t += step
    return ticks


def padded_domain(values, pad_frac=0.18, snap=0.05):
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * pad_frac, snap)
    lo = math.floor((lo - pad) / snap) * snap
    hi = math.ceil((hi + pad) / snap) * snap
    return max(0.0, lo), min(1.0, hi)


def legend_html(countries, label_fn=None):
    items = []
    for c in countries:
        swatch = (f'<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'
                  f'{marker(MARKERS[c], 8, 8, 6, COLORS[c])}</svg>')
        label = label_fn(c) if label_fn else c
        items.append(f'<li>{swatch}<span>{esc(label)}</span></li>')
    return f'<ul class="legend">{"".join(items)}</ul>'


def table_view(caption, headers, rows):
    head = "".join(f"<th scope=\"col\">{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(
            f'<th scope="row">{esc(c)}</th>' if i == 0 else f"<td>{esc(c)}</td>"
            for i, c in enumerate(r)
        ) + "</tr>"
        for r in rows
    )
    return (f'<details class="tableview"><summary>{esc(caption)}</summary>'
            f'<div class="scrollx"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div></details>")


# --------------------------------------------------------------------------- #
# chart 1 - cultural map
# --------------------------------------------------------------------------- #

def chart_cultural_map(stats):
    W, H = 680, 520
    m = {"l": 84, "r": 30, "t": 28, "b": 76}
    pw, ph = W - m["l"] - m["r"], H - m["t"] - m["b"]

    xs = [stats[c]["secular_values"] for c in COUNTRIES]
    ys = [stats[c]["emancipative_values"] for c in COUNTRIES]
    x0, x1 = padded_domain(xs)
    y0, y1 = padded_domain(ys)

    def px(v):
        return m["l"] + (v - x0) / (x1 - x0) * pw

    def py(v):
        return m["t"] + ph - (v - y0) / (y1 - y0) * ph

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Average secular and emancipative values for five countries">']

    for t in nice_ticks(x0, x1):
        parts.append(f'<line class="grid" x1="{px(t):.2f}" y1="{m["t"]}" '
                     f'x2="{px(t):.2f}" y2="{m["t"] + ph}"/>')
        parts.append(f'<text class="tick" x="{px(t):.2f}" y="{m["t"] + ph + 26}" '
                     f'text-anchor="middle">{f_index(t)}</text>')
    for t in nice_ticks(y0, y1):
        parts.append(f'<line class="grid" x1="{m["l"]}" y1="{py(t):.2f}" '
                     f'x2="{m["l"] + pw}" y2="{py(t):.2f}"/>')
        parts.append(f'<text class="tick" x="{m["l"] - 12}" y="{py(t) + 6:.2f}" '
                     f'text-anchor="end">{f_index(t)}</text>')

    parts.append(f'<text class="axis" x="{m["l"] + pw / 2:.0f}" y="{H - 18}" '
                 f'text-anchor="middle">Secular values (0 = traditional, 1 = secular)</text>')
    parts.append(f'<text class="axis" transform="translate(24 {m["t"] + ph / 2:.0f}) '
                 f'rotate(-90)" text-anchor="middle">Emancipative values '
                 f'(0 = low, 1 = high)</text>')

    # India and Turkey sit close together, so India's label goes to its left
    # rather than below, where it would land on Turkey's point.
    offsets = {"China": (0, -24, "middle"), "India": (-15, 6, "end"),
               "Kazakhstan": (0, 30, "middle"), "Singapore": (0, -24, "middle"),
               "Turkey": (0, 30, "middle")}
    for c in COUNTRIES:
        x, y = px(stats[c]["secular_values"]), py(stats[c]["emancipative_values"])
        tip = (f'{c}: secular {f_index(stats[c]["secular_values"])}, '
               f'emancipative {f_index(stats[c]["emancipative_values"])} '
               f'(n = {f_int(stats[c]["n"])})')
        parts.append(marker(MARKERS[c], x, y, 9, COLORS[c],
                            stroke="var(--surface)", stroke_width=2, title=tip))
        dx, dy, anchor = offsets[c]
        parts.append(f'<text class="pointlabel" x="{x + dx:.2f}" y="{y + dy:.2f}" '
                     f'text-anchor="{anchor}">{esc(c)}</text>')
    parts.append("</svg>")

    rows = [(c, f_index(stats[c]["secular_values"]),
             f_index(stats[c]["emancipative_values"]), f_int(stats[c]["n"]))
            for c in COUNTRIES]
    return "".join(parts), rows


# --------------------------------------------------------------------------- #
# chart 2 - radar
# --------------------------------------------------------------------------- #

def chart_radar(radar):
    W, H = 680, 600
    cx, cy, R = W / 2, 292, 178
    n = len(RADAR_AXES)

    def point(i, v):
        a = math.radians(-90 + i * 360 / n)
        return cx + math.cos(a) * R * v, cy + math.sin(a) * R * v

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Radar chart of six normalised measures for five countries">']

    for ring in (0.2, 0.4, 0.6, 0.8, 1.0):
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in
                       (point(i, ring) for i in range(n)))
        parts.append(f'<polygon class="grid" points="{pts}" fill="none"/>')
    for i in range(n):
        x, y = point(i, 1.0)
        parts.append(f'<line class="grid" x1="{cx:.2f}" y1="{cy:.2f}" '
                     f'x2="{x:.2f}" y2="{y:.2f}"/>')
    for ring in (0.5, 1.0):
        x, y = point(0, ring)
        parts.append(f'<text class="tick" x="{x + 8:.2f}" y="{y + 4:.2f}" '
                     f'text-anchor="start">{f_index(ring)}</text>')

    for i, (label, _, _) in enumerate(RADAR_AXES):
        a = math.radians(-90 + i * 360 / n)
        lx, ly = cx + math.cos(a) * (R + 34), cy + math.sin(a) * (R + 30)
        anchor = "middle"
        if math.cos(a) > 0.3:
            anchor = "start"
        elif math.cos(a) < -0.3:
            anchor = "end"
        words = label.split(" ")
        if len(words) > 1:
            parts.append(f'<text class="axislabel" x="{lx:.2f}" y="{ly - 8:.2f}" '
                         f'text-anchor="{anchor}">{esc(words[0])}'
                         f'<tspan x="{lx:.2f}" dy="19">{esc(" ".join(words[1:]))}'
                         f"</tspan></text>")
        else:
            parts.append(f'<text class="axislabel" x="{lx:.2f}" y="{ly:.2f}" '
                         f'text-anchor="{anchor}">{esc(label)}</text>')

    for c in COUNTRIES:
        vals = [radar[c][key] for _, key, _ in RADAR_AXES]
        pts = [point(i, v) for i, v in enumerate(vals)]
        poly = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        dash = "" if DASHES[c] == "none" else f' stroke-dasharray="{DASHES[c]}"'
        parts.append(f'<polygon points="{poly}" fill="none" stroke="{COLORS[c]}" '
                     f'stroke-width="2" stroke-linejoin="round"{dash}/>')
        for i, (x, y) in enumerate(pts):
            label, _, _ = RADAR_AXES[i]
            parts.append(marker(MARKERS[c], x, y, 5.5, COLORS[c],
                                stroke="var(--surface)", stroke_width=2,
                                title=f"{c} - {label}: {f_index(vals[i])}"))
    parts.append("</svg>")

    headers = ["Country"] + [lbl for lbl, _, _ in RADAR_AXES]
    rows = [[c] + [f_index(radar[c][key]) for _, key, _ in RADAR_AXES]
            for c in COUNTRIES]
    return "".join(parts), headers, rows


# --------------------------------------------------------------------------- #
# chart 3 - individual scatter, China vs India
# --------------------------------------------------------------------------- #

def chart_individual_scatter(sample, stats):
    W, H = 680, 540
    m = {"l": 84, "r": 30, "t": 28, "b": 76}
    pw, ph = W - m["l"] - m["r"], H - m["t"] - m["b"]
    x0, x1, y0, y1 = 0.0, 1.0, 0.0, 1.0

    def px(v):
        return m["l"] + (v - x0) / (x1 - x0) * pw

    def py(v):
        return m["t"] + ph - (v - y0) / (y1 - y0) * ph

    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Scatter of individual respondents from China and India">']
    for t in nice_ticks(x0, x1, 5):
        parts.append(f'<line class="grid" x1="{px(t):.2f}" y1="{m["t"]}" '
                     f'x2="{px(t):.2f}" y2="{m["t"] + ph}"/>')
        parts.append(f'<text class="tick" x="{px(t):.2f}" y="{m["t"] + ph + 26}" '
                     f'text-anchor="middle">{f_index(t)}</text>')
    for t in nice_ticks(y0, y1, 5):
        parts.append(f'<line class="grid" x1="{m["l"]}" y1="{py(t):.2f}" '
                     f'x2="{m["l"] + pw}" y2="{py(t):.2f}"/>')
        parts.append(f'<text class="tick" x="{m["l"] - 12}" y="{py(t) + 6:.2f}" '
                     f'text-anchor="end">{f_index(t)}</text>')
    parts.append(f'<text class="axis" x="{m["l"] + pw / 2:.0f}" y="{H - 18}" '
                 f'text-anchor="middle">Secular values</text>')
    parts.append(f'<text class="axis" transform="translate(24 {m["t"] + ph / 2:.0f}) '
                 f'rotate(-90)" text-anchor="middle">Emancipative values</text>')

    for c in SCATTER_COUNTRIES:
        parts.append(f'<g opacity="0.55">')
        for r in sample[c]:
            parts.append(marker(MARKERS[c], px(r["secular_values"]),
                                py(r["emancipative_values"]), 3.6, COLORS[c]))
        parts.append("</g>")

    # The two means are close, so one label goes above and one below.
    label_dy = {"China": -26, "India": 38}
    for c in SCATTER_COUNTRIES:
        x = px(stats[c]["secular_values"])
        y = py(stats[c]["emancipative_values"])
        tip = (f'{c} average: secular {f_index(stats[c]["secular_values"])}, '
               f'emancipative {f_index(stats[c]["emancipative_values"])}')
        parts.append(marker(MARKERS[c], x, y, 13, COLORS[c],
                            stroke="var(--surface)", stroke_width=3, title=tip))
        parts.append(f'<text class="pointlabel" x="{x:.2f}" '
                     f'y="{y + label_dy[c]:.2f}" '
                     f'text-anchor="middle">{esc(c)} avg</text>')
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# chart 4 - Singapore heatmap (plain HTML/CSS grid)
# --------------------------------------------------------------------------- #

def chart_heatmap(counts, vmax):
    # Single hue, light to dark. Step 0 is the empty-cell surface.
    steps = ["#f2f7fb", "#dbe9f6", "#bcd8ef", "#94c1e3", "#68a6d4",
             "#4189c2", "#2a6ca8", "#1a5288", "#0f3c68"]
    cells = ['<div class="hm-corner" aria-hidden="true"></div>']
    for fin in range(1, 11):
        cells.append(f'<div class="hm-colhead">{fin}</div>')
    for life in range(10, 0, -1):
        cells.append(f'<div class="hm-rowhead">{life}</div>')
        for fin in range(1, 11):
            n = counts.get((life, fin), 0)
            idx = 0 if n == 0 else 1 + min(len(steps) - 2,
                                           int(n / vmax * (len(steps) - 1.001)))
            dark = idx >= 6
            cls = "hm-cell dark" if dark else "hm-cell"
            tip = (f"Life satisfaction {life}, financial satisfaction {fin}: "
                   f"{f_int(n)} respondents")
            cells.append(f'<div class="{cls}" style="background:{steps[idx]}" '
                         f'title="{esc(tip)}">{n if n else ""}</div>')
    grid = (
        '<div class="hm-wrap">'
        '<div class="hm-ylabel"><span>Life satisfaction (1-10)</span></div>'
        '<div class="hm-main">'
        '<div class="heatmap" role="img" aria-label="10 by 10 heatmap of '
        'life satisfaction against financial satisfaction in Singapore">'
        f'{"".join(cells)}</div>'
        '<p class="hm-axis-x">Financial satisfaction (1-10)</p>'
        "</div></div>"
    )
    scale = "".join(f'<span style="background:{s}"></span>' for s in steps)
    legend = (f'<div class="hm-legend"><span class="hm-legend-lab">0</span>'
              f'<div class="hm-ramp">{scale}</div>'
              f'<span class="hm-legend-lab">{f_int(vmax)} respondents</span></div>')
    return grid, legend


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def overlap_coefficient(a, b, bins=20, lo=0.0, hi=1.0):
    """Histogram-intersection overlap of two distributions, 0-1."""
    def hist(xs):
        h = [0] * bins
        for x in xs:
            k = min(bins - 1, max(0, int((x - lo) / (hi - lo) * bins)))
            h[k] += 1
        return [c / len(xs) for c in h]
    ha, hb = hist(a), hist(b)
    return sum(min(p, q) for p, q in zip(ha, hb))


CSS = """
:root{
  color-scheme: light dark;
  --surface:#ffffff; --surface-2:#f6f8fa; --ink:#14181d; --ink-2:#414a55;
  --ink-3:#6b7681; --rule:#e3e8ee; --grid:#e8ecf1; --accent:#0f3c68;
  --maxw:920px;
}
@media (prefers-color-scheme: dark){
  :root{
    --surface:#14181d; --surface-2:#1c2127; --ink:#eef2f6; --ink-2:#c2cbd5;
    --ink-3:#8b96a2; --rule:#2a313a; --grid:#2a313a; --accent:#9ec8ea;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--surface); color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
.wrap{max-width:var(--maxw); margin:0 auto; padding:40px 20px 80px}
header{border-bottom:1px solid var(--rule); padding-bottom:26px; margin-bottom:34px}
h1{font-size:clamp(1.6rem,4.2vw,2.3rem); line-height:1.2; margin:0 0 6px; letter-spacing:-0.02em}
.sub{color:var(--ink-3); font-size:.95rem; margin:0}
h2{font-size:clamp(1.15rem,2.6vw,1.4rem); margin:0 0 4px; letter-spacing:-0.01em}
h3{font-size:1rem; margin:0 0 10px; color:var(--ink-2)}
p{margin:0 0 14px; color:var(--ink-2); max-width:68ch}
a{color:var(--accent)}
.callout{
  background:var(--surface-2); border:1px solid var(--rule); border-left:3px solid var(--accent);
  border-radius:8px; padding:16px 18px; margin:0 0 24px;
}
.callout p:last-child{margin-bottom:0}
section{margin:0 0 56px}
.eyebrow{
  font-size:.72rem; letter-spacing:.09em; text-transform:uppercase;
  color:var(--ink-3); margin:0 0 6px; font-weight:600;
}
figure{margin:20px 0 0}
.chart{width:100%; height:auto; display:block; overflow:visible}
.chart .grid{stroke:var(--grid); stroke-width:1; fill:none}
.chart text{font-family:inherit}
.chart .tick{font-size:15px; fill:var(--ink-3); font-variant-numeric:tabular-nums}
.chart .axis{font-size:16px; fill:var(--ink-2)}
.chart .axislabel{font-size:16px; fill:var(--ink-2)}
.chart .pointlabel{
  font-size:17px; fill:var(--ink); font-weight:600;
  paint-order:stroke; stroke:var(--surface); stroke-width:4px; stroke-linejoin:round;
}
.takeaway{
  margin:14px 0 0; padding:13px 16px; background:var(--surface-2);
  border:1px solid var(--rule); border-radius:8px; color:var(--ink);
  font-size:.95rem;
}
.takeaway b{font-weight:650}
.legend{
  list-style:none; display:flex; flex-wrap:wrap; gap:8px 20px;
  margin:16px 0 0; padding:0;
}
.legend li{display:flex; align-items:center; gap:7px; font-size:.9rem; color:var(--ink-2)}
.legend svg{flex:none; display:block}
.scrollx{overflow-x:auto; -webkit-overflow-scrolling:touch}
table{border-collapse:collapse; width:100%; font-size:.88rem; min-width:380px}
caption{text-align:left; color:var(--ink-3); font-size:.85rem; padding-bottom:8px}
th,td{
  text-align:right; padding:8px 10px; border-bottom:1px solid var(--rule);
  font-variant-numeric:tabular-nums; white-space:nowrap;
}
thead th{
  text-align:right; color:var(--ink-3); font-weight:600; font-size:.8rem;
  text-transform:uppercase; letter-spacing:.04em; border-bottom:1px solid var(--rule);
}
th:first-child,td:first-child,thead th:first-child{text-align:left; font-variant-numeric:normal}
tbody th{font-weight:600; color:var(--ink)}
code{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.9em;
  background:var(--surface-2); border:1px solid var(--rule); border-radius:4px; padding:1px 5px;
}
.tableview{margin:18px 0 0; font-size:.9rem}
.tableview summary{cursor:pointer; color:var(--ink-3); font-size:.85rem; padding:4px 0}
.tableview summary:hover{color:var(--ink)}
.tableview[open] summary{margin-bottom:10px}
.ok{color:#1a7f4b; font-weight:600}
@media (prefers-color-scheme: dark){ .ok{color:#4cc98a} }
.hm-wrap{display:flex; gap:6px; align-items:stretch; margin:18px 0 0}
.hm-main{flex:1; min-width:0}
.hm-ylabel{
  writing-mode:vertical-rl; transform:rotate(180deg);
  display:flex; align-items:center; justify-content:center;
  font-size:.82rem; color:var(--ink-2); flex:none;
}
.heatmap{
  display:grid; grid-template-columns:1.7rem repeat(10,minmax(0,1fr)); gap:2px;
}
.hm-cell{
  aspect-ratio:1; display:flex; align-items:center; justify-content:center;
  border-radius:3px; font-size:clamp(9px,1.5vw,12px); color:#14181d;
  font-variant-numeric:tabular-nums;
}
.hm-cell.dark{color:#ffffff}
.hm-colhead,.hm-rowhead{
  display:flex; align-items:center; justify-content:center;
  font-size:clamp(9px,1.5vw,12px); color:var(--ink-3);
  font-variant-numeric:tabular-nums;
}
.hm-axis-x{text-align:center; font-size:.85rem; color:var(--ink-2); margin:8px 0 0}
.hm-legend{display:flex; align-items:center; gap:10px; margin:16px 0 0; flex-wrap:wrap}
.hm-ramp{display:flex; gap:2px}
.hm-ramp span{width:22px; height:12px; border-radius:2px}
.hm-legend-lab{font-size:.8rem; color:var(--ink-3)}
footer{border-top:1px solid var(--rule); padding-top:22px; color:var(--ink-3); font-size:.85rem}
footer p{color:var(--ink-3); font-size:.85rem}
@media (max-width:560px){
  .wrap{padding:26px 14px 56px}
  .chart .tick{font-size:17px}
  .chart .axis,.chart .axislabel{font-size:18px}
  .chart .pointlabel{font-size:19px}
}
"""


def build():
    rng = random.Random(SEED)
    columns, rows = load_rows()
    n_raw = len(rows)

    cols_profile = profile(columns, rows)

    # --- duplicate checks (before cleaning) ---
    full_keys = Counter(tuple(r[c] for c in columns) for r in rows)
    dup_full = sum(v - 1 for v in full_keys.values() if v > 1)
    id_keys = Counter(r[ID_COLUMN] for r in rows)
    dup_id = sum(v - 1 for v in id_keys.values() if v > 1)

    # --- missing values: drop any row with a blank cell ---
    missing_by_col = [(c["name"], c["missing"]) for c in cols_profile
                      if c["missing"] > 0]
    missing_by_col.sort(key=lambda t: -t[1])
    clean = [r for r in rows if all(r[c] != "" for c in columns)]
    n_clean = len(clean)
    dropped = n_raw - n_clean

    per_country_raw = Counter(r["country"] for r in rows)
    per_country_clean = Counter(r["country"] for r in clean)

    # --- typed records ---
    num_cols = ["age", "life_satisfaction", "freedom_of_choice",
                "emancipative_values", "importance_of_god",
                "financial_satisfaction", "secular_values"]
    recs = []
    for r in clean:
        rec = {"country": r["country"], ID_COLUMN: int(float(r[ID_COLUMN])),
               "trust_people": r["trust_people"]}
        for c in num_cols:
            rec[c] = float(r[c])
        recs.append(rec)
    by_country = {c: [r for r in recs if r["country"] == c] for c in COUNTRIES}

    # --- country aggregates ---
    stats = {}
    for c in COUNTRIES:
        g = by_country[c]
        stats[c] = {
            "n": len(g),
            "secular_values": mean([r["secular_values"] for r in g]),
            "emancipative_values": mean([r["emancipative_values"] for r in g]),
            "life_satisfaction": mean([r["life_satisfaction"] for r in g]),
            "importance_of_god": mean([r["importance_of_god"] for r in g]),
            "financial_satisfaction": mean([r["financial_satisfaction"] for r in g]),
            "trust_share": sum(1 for r in g if r["trust_people"] == "Trusted") / len(g),
        }

    radar = {c: {
        "life_satisfaction": stats[c]["life_satisfaction"] / 10,
        "trust_people": stats[c]["trust_share"],
        "importance_of_god": stats[c]["importance_of_god"] / 10,
        "emancipative_values": stats[c]["emancipative_values"],
        "secular_values": stats[c]["secular_values"],
        "financial_satisfaction": stats[c]["financial_satisfaction"] / 10,
    } for c in COUNTRIES}

    # --- seeded sample for the China vs India scatter ---
    sample = {}
    for c in SCATTER_COUNTRIES:
        pool = sorted(by_country[c], key=lambda r: r[ID_COLUMN])
        k = min(SAMPLE_PER_COUNTRY, len(pool))
        sample[c] = sorted(rng.sample(pool, k), key=lambda r: r[ID_COLUMN])

    ov_sec = overlap_coefficient([r["secular_values"] for r in by_country["China"]],
                                 [r["secular_values"] for r in by_country["India"]])
    ov_ema = overlap_coefficient([r["emancipative_values"] for r in by_country["China"]],
                                 [r["emancipative_values"] for r in by_country["India"]])

    # --- Singapore heatmap counts ---
    hm = Counter()
    for r in by_country[HEATMAP_COUNTRY]:
        hm[(int(r["life_satisfaction"]), int(r["financial_satisfaction"]))] += 1
    vmax = max(hm.values())
    hm_modal = max(hm.items(), key=lambda kv: (kv[1], kv[0]))
    sg_n = stats[HEATMAP_COUNTRY]["n"]
    diag = sum(v for (l, f), v in hm.items() if abs(l - f) <= 1)

    # ------------------------------------------------------------------ #
    # page
    # ------------------------------------------------------------------ #
    map_svg, map_rows = chart_cultural_map(stats)
    radar_svg, radar_headers, radar_rows = chart_radar(radar)
    scatter_svg = chart_individual_scatter(sample, stats)
    hm_grid, hm_legend = chart_heatmap(hm, vmax)

    most_secular = max(COUNTRIES, key=lambda c: stats[c]["secular_values"])
    least_secular = min(COUNTRIES, key=lambda c: stats[c]["secular_values"])
    most_eman = max(COUNTRIES, key=lambda c: stats[c]["emancipative_values"])
    least_eman = min(COUNTRIES, key=lambda c: stats[c]["emancipative_values"])
    most_trust = max(COUNTRIES, key=lambda c: stats[c]["trust_share"])
    least_trust = min(COUNTRIES, key=lambda c: stats[c]["trust_share"])
    most_god = max(COUNTRIES, key=lambda c: stats[c]["importance_of_god"])

    # data dictionary
    dict_rows = "".join(
        f'<tr><th scope="row"><code>{esc(c["name"])}</code></th>'
        f'<td>{esc(c["dtype"])}</td><td>{esc(c["note"])}</td>'
        f'<td>{f_int(c["n"])}</td><td>{f_int(c["missing"])}</td></tr>'
        for c in cols_profile
    )

    retention_rows = "".join(
        f'<tr><th scope="row">{esc(c)}</th><td>{f_int(per_country_raw[c])}</td>'
        f"<td>{f_int(per_country_clean[c])}</td>"
        f"<td>{f_pct(per_country_clean[c] / per_country_raw[c])}</td></tr>"
        for c in COUNTRIES
    )

    missing_list = ", ".join(f"<code>{esc(n)}</code> {f_int(k)}"
                             for n, k in missing_by_col)

    parts = []
    A = parts.append

    A('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n')
    A('<meta name="viewport" content="width=device-width, initial-scale=1">\n')
    A("<title>Values across five Asian countries - a synthetic WVS-style "
      "exploration</title>\n")
    A('<meta name="description" content="Exploratory analysis of a simulated, '
      'World Values Survey-style dataset covering China, India, Kazakhstan, '
      'Singapore and Turkey.">\n')
    A(f"<style>{CSS}</style>\n</head>\n<body>\n<div class=\"wrap\">\n")

    # header
    A("<header>\n<h1>Values across five Asian countries</h1>\n")
    A('<p class="sub">An exploratory analysis of simulated survey data &middot; '
      f"{f_int(n_clean)} complete responses</p>\n</header>\n")

    A('<div class="callout">\n')
    A("<p><b>This analysis uses synthetic (simulated) data.</b> Every row in "
      "<code>data/wvs-synthetic.csv</code> is fabricated. The dataset was generated to "
      "resemble the distributions and relationships found in the "
      '<a href="https://www.worldvaluessurvey.org/" rel="noopener">World Values '
      "Survey, Wave 7 (2017-2022)</a>, which serves only as the model it imitates - "
      "no real respondent data is used here. <b>Every pattern below is therefore "
      "illustrative only</b> and must not be read as evidence about any real "
      "country or population.</p>\n")
    A("<p>The five countries covered, one from each part of Asia, are "
      "<b>Turkey</b> (Middle East), <b>India</b> (South Asia), <b>Singapore</b> "
      "(Southeast Asia), <b>China</b> (East Asia) and <b>Kazakhstan</b> "
      "(Central Asia). Sample sizes differ by country.</p>\n")
    A('<p class="sub">Model for the simulation: Haerpfer, C., Inglehart, R., '
      "Moreno, A., Welzel, C., Kizilova, K., Diez-Medrano, J., Lagos, M., Norris, P., "
      "Ponarin, E. &amp; Puranen, B. (eds.), <i>World Values Survey: Round Seven - "
      "Country-Pooled Datafile</i>. Madrid &amp; Vienna: JD Systems Institute &amp; "
      'WVSA Secretariat. <a href="https://www.worldvaluessurvey.org/" '
      'rel="noopener">worldvaluessurvey.org</a></p>\n')
    A("</div>\n")

    # ---- section: the variables ----
    A("<section>\n<p class=\"eyebrow\">The data</p>\n<h2>Variables in the dataset"
      "</h2>\n")
    A(f"<p>The file holds {f_int(n_raw)} rows and {len(columns)} columns. "
      f"The table lists every variable with its data type and the number of "
      f"non-empty observations, as read from the raw file before any cleaning. "
      f"<code>{esc(ID_COLUMN)}</code> is excluded throughout: it is an identifier, "
      f"not a measurement, so it appears in no table or chart below.</p>\n")
    A('<div class="scrollx"><table><thead><tr><th scope="col">Variable</th>'
      '<th scope="col">Data type</th><th scope="col">Scale</th>'
      '<th scope="col">Observations</th><th scope="col">Missing</th></tr></thead>'
      f"<tbody>{dict_rows}</tbody></table></div>\n")
    A("</section>\n")

    # ---- section: quality checks ----
    A('<section>\n<p class="eyebrow">Quality checks</p>\n'
      "<h2>Duplicates and missing values</h2>\n")
    A(f"<h3>Duplicates</h3>\n<p>Checked two ways. Identical rows across all "
      f"{len(columns)} columns: <b>{f_int(dup_full)} found</b>. Repeated "
      f"<code>{esc(ID_COLUMN)}</code> values: <b>{f_int(dup_id)} found</b>. "
      f'<span class="ok">No duplicates were present, so no rows were removed on '
      f"this account.</span></p>\n")
    A(f"<h3>Missing values</h3>\n<p>{len(missing_by_col)} of the "
      f"{len(cols_profile)} analysed variables contain blanks "
      f"({missing_list}). Following the brief, any row with an empty cell "
      f"anywhere is dropped from the analysis: <b>{f_int(dropped)} rows removed "
      f"({f_pct(dropped / n_raw)} of the file)</b>, leaving <b>{f_int(n_clean)} "
      f"complete rows</b> ({f_pct(n_clean / n_raw)}) for every figure below.</p>\n")
    A(f"<p>Because blanks are not spread evenly, this listwise deletion hits the "
      f"countries unequally - {esc(min(COUNTRIES, key=lambda c: per_country_clean[c] / per_country_raw[c]))} "
      f"loses the largest share - which is worth keeping in mind when comparing "
      f"them.</p>\n")
    A('<div class="scrollx"><table><thead><tr><th scope="col">Country</th>'
      '<th scope="col">Rows in file</th><th scope="col">Complete rows</th>'
      f'<th scope="col">Retained</th></tr></thead><tbody>{retention_rows}'
      "</tbody></table></div>\n")
    A("</section>\n")

    # ---- chart 1 ----
    A('<section>\n<p class="eyebrow">Analysis 1</p>\n'
      "<h2>Cultural map: emancipative vs secular values</h2>\n")
    A("<p>Each point is one country's average, in the style of the "
      "Inglehart-Welzel cultural map. Right means more secular, up means more "
      "emancipative.</p>\n")
    A(f"<figure>{map_svg}{legend_html(COUNTRIES)}")
    A(f'<p class="takeaway">On these simulated averages, {esc(most_secular)} sits '
      f"furthest towards the secular end ({f_index(stats[most_secular]['secular_values'])}) "
      f"and {esc(least_secular)} the most traditional "
      f"({f_index(stats[least_secular]['secular_values'])}), while "
      f"{esc(most_eman)} scores highest on emancipative values "
      f"({f_index(stats[most_eman]['emancipative_values'])}) and {esc(least_eman)} "
      f"lowest ({f_index(stats[least_eman]['emancipative_values'])}). The five "
      f"countries spread along both axes rather than clustering, but the gaps are "
      f"modest - all five averages fall within roughly "
      f"{f_index(max(stats[c]['secular_values'] for c in COUNTRIES) - min(stats[c]['secular_values'] for c in COUNTRIES))} "
      f"of each other on the secular axis.</p>")
    A(table_view("Show the numbers",
                 ["Country", "Secular values (avg)", "Emancipative values (avg)",
                  "Respondents"], map_rows))
    A("</figure>\n</section>\n")

    # ---- chart 2 ----
    A('<section>\n<p class="eyebrow">Analysis 2</p>\n'
      "<h2>Value fingerprints across six measures</h2>\n")
    A("<p>Six measures, each rescaled to run 0-1 so they share one axis: the "
      "three 1-10 satisfaction and religiosity items are divided by 10, "
      "<code>trust_people</code> is the share answering &ldquo;Trusted&rdquo;, and "
      "the two value indices are already on a 0-1 scale. Each country has its own "
      "colour, marker and line style.</p>\n")
    A(f"<figure>{radar_svg}{legend_html(COUNTRIES)}")
    A(f'<p class="takeaway">The fingerprints differ most on trust and religiosity: '
      f"{esc(most_trust)} reports much the highest share trusting others "
      f"({f_pct(stats[most_trust]['trust_share'])} vs "
      f"{f_pct(stats[least_trust]['trust_share'])} in {esc(least_trust)}), and "
      f"{esc(most_god)} rates the importance of god highest "
      f"({f_scale(stats[most_god]['importance_of_god'])} out of 10). The value "
      f"indices, by contrast, sit in a narrow band for all five countries, so the "
      f"shapes overlap heavily on the emancipative and secular spokes.</p>")
    A(table_view("Show the numbers (all values normalised 0-1)",
                 radar_headers, radar_rows))
    A("</figure>\n</section>\n")

    # ---- chart 3 ----
    A('<section>\n<p class="eyebrow">Analysis 3</p>\n'
      "<h2>Individual respondents: China vs India</h2>\n")
    A(f"<p>The same two axes as the cultural map, but one point per person - a "
      f"random sample of {SAMPLE_PER_COUNTRY} respondents from each country "
      f"(seeded, so this figure is reproducible) drawn from "
      f"{f_int(stats['China']['n'])} Chinese and {f_int(stats['India']['n'])} "
      f"Indian complete responses. The large outlined markers are each country's "
      f"average across all of its respondents, not just the sample.</p>\n")
    A(f"<figure>{scatter_svg}")
    A(legend_html(list(SCATTER_COUNTRIES),
                  lambda c: f"{c} (n = {f_int(stats[c]['n'])})"))
    A(f'<p class="takeaway">The two clouds sit almost on top of each other: the '
      f"country averages differ by only "
      f"{f_index(abs(stats['China']['secular_values'] - stats['India']['secular_values']))} "
      f"on secular values and "
      f"{f_index(abs(stats['China']['emancipative_values'] - stats['India']['emancipative_values']))} "
      f"on emancipative values, and the full distributions overlap by "
      f"{f_pct(ov_sec)} and {f_pct(ov_ema)} respectively. Differences between "
      f"individuals within either country are far larger than the difference "
      f"between the two national averages, so the averages say very little about "
      f"any one respondent.</p>")
    A("</figure>\n</section>\n")

    # ---- chart 4 ----
    A('<section>\n<p class="eyebrow">Analysis 4</p>\n'
      "<h2>Life vs financial satisfaction in Singapore</h2>\n")
    A(f"<p>All {f_int(sg_n)} complete Singaporean responses, cross-tabulated: "
      f"rows are life satisfaction (10 at the top), columns are financial "
      f"satisfaction. Darker cells hold more respondents.</p>\n")
    A(f"<figure>{hm_grid}")
    A(hm_legend)
    A(f'<p class="takeaway">The mass runs along the diagonal: '
      f"{f_pct(diag / sg_n)} of Singaporean respondents rate the two within one "
      f"point of each other, and the single most common combination is life "
      f"{hm_modal[0][0]} with financial {hm_modal[0][1]} "
      f"({f_int(hm_modal[1])} respondents). Satisfaction with life and with one's "
      f"finances move together in this simulated data, and both cluster in the "
      f"upper-middle of the scale rather than at the extremes.</p>")
    A("</figure>\n</section>\n")

    # ---- footer ----
    A("<footer>\n")
    A(f"<p>Generated from <code>data/wvs-synthetic.csv</code> by "
      f"<code>generate_index.py</code> (random seed {SEED}, so the page rebuilds "
      f"identically every run). This page is self-contained: all results are "
      f"embedded, no data file is read and no network request is made at "
      f"view time.</p>\n")
    A("<p>Reminder: the underlying data is <b>simulated</b>. Nothing here is a "
      "finding about a real country.</p>\n")
    A("</footer>\n")

    A("</div>\n</body>\n</html>\n")

    OUT_PATH.write_text("".join(parts), encoding="utf-8", newline="\n")

    # console report, so the run itself is auditable
    print(f"rows read ................. {n_raw:,}")
    print(f"duplicate rows ............ {dup_full:,}")
    print(f"duplicate {ID_COLUMN} ... {dup_id:,}")
    print(f"rows dropped (any blank) .. {dropped:,}")
    print(f"complete rows used ........ {n_clean:,}")
    for c in COUNTRIES:
        print(f"  {c:<11} {per_country_raw[c]:>5,} -> {per_country_clean[c]:>5,}"
              f"   secular {stats[c]['secular_values']:.4f}"
              f"   emancipative {stats[c]['emancipative_values']:.4f}"
              f"   trust {stats[c]['trust_share']:.4f}")
    print(f"Singapore heatmap cells ... {sum(hm.values()):,} (max cell {vmax})")
    print(f"China/India overlap ....... secular {ov_sec:.4f}  "
          f"emancipative {ov_ema:.4f}")
    print(f"wrote {OUT_PATH.name} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
