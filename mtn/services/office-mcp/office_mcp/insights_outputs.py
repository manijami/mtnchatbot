"""Excel insights: files built from a saved analysis run. Every number comes from the run.

- ``check_numbers``: insight text from the model may only contain numbers found in the results.
- Charts (PNG, MTN colours), a one-page infographic (PNG + PDF) and a static HTML dashboard.
- PowerPoint and Excel specs for the existing, validated document pipeline (native charts).
"""

from __future__ import annotations

import base64
import html
import io
import math
import re
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from .errors import ToolError  # noqa: E402

YELLOW, INK, GREY, LIGHT, RED, GREEN = "#FFCB05", "#1F1F1F", "#5C5C5C", "#E3E3E3", "#B3261E", "#1B6B34"
FONT = "Liberation Sans"
MAX_CHART_ITEMS = 15
MAX_INSIGHTS = 5
CHART_TYPES = {"group_summary", "top_n", "share_of_total", "time_trend", "period_change", "distribution"}

# -- number check ----------------------------------------------------------------------------------------

_DATEISH = re.compile(r"\b\d{4}-(?:Q[1-4]|\d{2}(?:-\d{2})?)\b|\bQ[1-4]\b|week of \d{4}-\d{2}-\d{2}", re.IGNORECASE)
_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-+−])?(?:R\s?)?(?P<num>\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?"
    r"(?P<unit>%|percent\b|bn\b|billion\b|m\b|million\b|k\b|thousand\b)?",
    re.IGNORECASE,
)
_SCALE = {"bn": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6, "k": 1e3, "thousand": 1e3}


def _run_values(run: dict) -> tuple[list[float], set[str]]:
    values: list[float] = []
    labels: set[str] = set()
    for result in run.get("results", []):
        for row in result.get("table", {}).get("rows", []):
            for cell in row:
                if isinstance(cell, (int, float)) and not isinstance(cell, bool) and not math.isnan(cell):
                    values.append(float(cell))
                elif isinstance(cell, str):
                    labels.add(cell.lower())
        for key in ("rows_used", "total"):
            if isinstance(result.get(key), (int, float)):
                values.append(float(result[key]))
        values.extend(float(v) for v in (result.get("rows_left_out") or {}).values())
    return values, labels


def check_numbers(texts: list[str], run: dict) -> None:
    """Every number in the insight texts must match a computed value (at the precision written)."""
    values, labels = _run_values(run)
    # Category names with digits ("Fibre 100", a distribution bin) are labels, not quoted numbers.
    named = sorted((label for label in labels if any(ch.isdigit() for ch in label)), key=len, reverse=True)
    label_pattern = re.compile("|".join(rf"(?<!\w){re.escape(label)}(?!\w)" for label in named), re.IGNORECASE) if named else None
    problems = []
    for text in texts:
        scrubbed = label_pattern.sub(" ", text) if label_pattern else text
        scrubbed = _DATEISH.sub(" ", scrubbed)
        for match in _NUMBER.finditer(scrubbed):
            raw = match.group("num")
            number = float(raw.replace(",", "").replace(" ", ""))
            unit = (match.group("unit") or "").lower()
            if match.group("sign") in ("-", "−"):
                number = -number
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            if not unit and float(abs(number)).is_integer() and abs(number) <= 10:
                continue  # small counts in prose ("top 3", "5 regions")
            if not unit and raw.isdigit() and len(raw) == 4 and raw in " ".join(labels):
                continue  # a year that appears in the results' labels
            scale = _SCALE.get(unit, 1.0)
            tolerance = 0.5 * 10 ** (-decimals) + 1e-9
            ok = any(abs(v / scale - number) <= tolerance or abs(abs(v) / scale - abs(number)) <= tolerance for v in values)
            if not ok and unit in ("%", "percent"):
                ok = any(abs(v * 100 - number) <= tolerance for v in values)
            if not ok:
                problems.append(match.group(0).strip())
    if problems:
        shown = ", ".join(f"'{p}'" for p in dict.fromkeys(problems))
        raise ToolError(
            f"These numbers in the insights are not in the analysis results: {shown}. Use only numbers from "
            "analyse_workbook (rounded as shown there), or run another analysis that computes them."
        )


# -- charts ------------------------------------------------------------------------------------------------


def _figure(width=8.0, height=4.5) -> Figure:
    fig = Figure(figsize=(width, height), dpi=200)
    fig.patch.set_facecolor("white")
    return fig


def _style(ax, title: str):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, fontfamily=FONT, pad=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LIGHT)
    ax.spines["bottom"].set_color(LIGHT)
    ax.tick_params(colors=GREY, labelsize=9)
    for axis in (ax.xaxis, ax.yaxis):
        # Value axes read 500k / 1.5m, not "1e6"; category axes keep their labels.
        if isinstance(axis.get_major_formatter(), matplotlib.ticker.ScalarFormatter):
            axis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _pos: _tick(v)))
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT)


def _tick(value: float) -> str:
    """Axis tick text: 0, 500k, 1.5m (no scientific offset)."""
    for scale, unit in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(value) >= scale:
            return f"{value / scale:g}{unit}"
    return f"{value:g}"


def _fmt(value) -> str:
    if value is None:
        return "–"
    value = float(value)
    if abs(value) >= 1e9:
        return f"{value / 1e9:.1f}bn"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f}m"
    if abs(value) >= 1e4:
        return f"{value / 1e3:.0f}k"
    return f"{value:,.2f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{int(value):,}"


def source_line(run: dict, result: dict) -> str:
    cols = ", ".join(result.get("columns_used", []))
    return f"Source: {run.get('file')} › {result.get('sheet')} › {cols} · {result.get('rows_used', 0):,} rows"


def chartable(run: dict) -> list[dict]:
    return [r for r in run.get("results", []) if r.get("type") in CHART_TYPES and r.get("table", {}).get("rows") and r.get("rows_used")]


def draw_chart(ax, run: dict, result: dict, compact: bool = False) -> None:
    rows = result["table"]["rows"]
    kind = result["type"]
    title = result.get("title", "")
    if kind in ("time_trend",):
        rows = rows[-24:]
        labels, values = [r[0] for r in rows], [r[1] or 0 for r in rows]
        ax.plot(range(len(values)), values, color=INK, linewidth=2, marker="o", markerfacecolor=YELLOW, markeredgecolor=INK, markersize=6)
        ax.fill_between(range(len(values)), values, color=YELLOW, alpha=0.25)
        step = max(1, len(labels) // 8)
        ax.set_xticks(range(0, len(labels), step), [labels[i] for i in range(0, len(labels), step)], rotation=0)
        ax.annotate(_fmt(values[-1]), (len(values) - 1, values[-1]), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9, color=INK)
        ax.grid(axis="y", color=LIGHT, linewidth=0.8)
    elif kind == "period_change":
        rows = rows[-12:]
        labels, values = [r[0] for r in rows], [r[4] or 0 for r in rows]
        ax.bar(range(len(values)), values, color=[GREEN if v >= 0 else RED for v in values], edgecolor=INK, linewidth=0.5)
        ax.axhline(0, color=INK, linewidth=0.8)
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        title = f"{title} (change)"
    elif kind == "distribution":
        rows = rows[:MAX_CHART_ITEMS]
        labels, values = [str(r[0]) for r in rows], [r[1] for r in rows]
        ax.bar(range(len(values)), values, color=YELLOW, edgecolor=INK, linewidth=0.6)
        ax.set_xticks(range(len(labels)), labels, rotation=35 if len(labels) > 5 else 0, ha="right" if len(labels) > 5 else "center")
        for i, v in enumerate(values):
            ax.text(i, v, _fmt(v), ha="center", va="bottom", fontsize=8, color=INK)
    else:  # group_summary, top_n, share_of_total: horizontal bars, largest on top
        rows = rows[:MAX_CHART_ITEMS]
        labels = [str(r[0])[:28] for r in rows][::-1]
        values = [r[1] or 0 for r in rows][::-1]
        shares = [r[2] for r in rows][::-1] if kind == "share_of_total" else None
        ax.barh(range(len(values)), values, color=YELLOW, edgecolor=INK, linewidth=0.6)
        ax.set_yticks(range(len(labels)), labels)
        for i, v in enumerate(values):
            text = _fmt(v) + (f"  ({shares[i]}%)" if shares else "")
            ax.text(v, i, " " + text, va="center", fontsize=8, color=INK)
        ax.set_xlim(0, max(values or [1]) * 1.22 if max(values or [0]) > 0 else 1)
        ax.grid(axis="x", color=LIGHT, linewidth=0.8)
    _style(ax, title[:70])
    if not compact:
        ax.figure.text(0.01, 0.01, source_line(run, result), fontsize=7, color=GREY, fontfamily=FONT)


def chart_png(run: dict, result: dict) -> bytes:
    fig = _figure()
    ax = fig.add_axes([0.2 if result["type"] in ("group_summary", "top_n", "share_of_total") else 0.08, 0.18, 0.75, 0.7])
    draw_chart(ax, run, result)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()


# -- headline figures -----------------------------------------------------------------------------------------


def headlines(run: dict) -> list[tuple[str, str, str]]:
    """Up to 4 (label, value, detail) tiles, read straight from the results."""
    tiles = []
    for r in run.get("results", []):
        rows = r.get("table", {}).get("rows") or []
        if not rows or not r.get("rows_used"):
            continue
        if r["type"] == "share_of_total":
            tiles.append((f"Largest share · {r['table']['columns'][0]}", f"{rows[0][2]}%", f"{rows[0][0]}: {_fmt(rows[0][1])}"))
        elif r["type"] in ("group_summary", "top_n"):
            tiles.append((r["title"][:40], _fmt(rows[0][1]), f"Highest: {rows[0][0]}"))
        elif r["type"] == "time_trend":
            tiles.append((f"{r['title'][:32]} · latest", _fmt(rows[-1][1]), str(rows[-1][0])))
        elif r["type"] == "period_change":
            last = rows[-1]
            change = f"{'+' if (last[4] or 0) >= 0 else ''}{last[5]}%" if last[5] is not None else _fmt(last[4])
            tiles.append((f"Change · {last[0]} vs {last[2]}", change, f"{_fmt(last[1])} vs {_fmt(last[3])}"))
        if len(tiles) == 4:
            break
    return tiles


# -- infographic ---------------------------------------------------------------------------------------------


def infographic(run: dict, title: str, insights: list[str], logo: bytes | None) -> tuple[bytes, bytes]:
    """A one-page A4 portrait summary as (PNG, PDF)."""
    fig = Figure(figsize=(8.27, 11.69), dpi=150)
    fig.patch.set_facecolor("white")
    band = fig.add_axes([0, 0.9, 1, 0.1])
    band.set_axis_off()
    band.add_patch(matplotlib.patches.Rectangle((0, 0), 1, 1, color=YELLOW, transform=band.transAxes))
    band.text(0.04 if not logo else 0.17, 0.58, title[:60], fontsize=19, fontweight="bold", color="black", fontfamily=FONT, va="center")
    band.text(0.04 if not logo else 0.17, 0.25, f"{run.get('file')} · {date.today().strftime('%d %B %Y')}", fontsize=10, color="black", fontfamily=FONT, va="center")
    if logo:
        from PIL import Image

        image = Image.open(io.BytesIO(logo))
        holder = fig.add_axes([0.03, 0.905, 0.11, 0.09])
        holder.imshow(image)
        holder.set_axis_off()
    tiles = headlines(run)
    for i, (label, value, detail) in enumerate(tiles):
        ax = fig.add_axes([0.04 + i * 0.235, 0.775, 0.215, 0.1])
        ax.set_axis_off()
        ax.add_patch(matplotlib.patches.FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.08",
                                                       facecolor="#FFF5CC", edgecolor=YELLOW, transform=ax.transAxes))
        ax.text(0.07, 0.78, label[:30], fontsize=7.5, color=GREY, fontfamily=FONT, transform=ax.transAxes)
        ax.text(0.07, 0.38, value, fontsize=17, fontweight="bold", color=INK, fontfamily=FONT, transform=ax.transAxes)
        ax.text(0.07, 0.12, detail[:34], fontsize=7, color=GREY, fontfamily=FONT, transform=ax.transAxes)
    charts = chartable(run)[:2]
    for i, result in enumerate(charts):
        horizontal = result["type"] in ("group_summary", "top_n", "share_of_total")
        ax = fig.add_axes([0.22 if horizontal else 0.08, 0.53 - i * 0.235, 0.7 if horizontal else 0.86, 0.18])
        draw_chart(ax, run, result, compact=True)
    box = fig.add_axes([0.04, 0.06, 0.92, 0.2])
    box.set_axis_off()
    box.text(0, 0.95, "Key insights", fontsize=13, fontweight="bold", color=INK, fontfamily=FONT, va="top")
    y = 0.78
    for line in (insights or ["See the analysis results in the chat."])[:MAX_INSIGHTS]:
        wrapped = _wrap(line, 105)
        box.text(0.01, y, "•  " + wrapped, fontsize=9, color=INK, fontfamily=FONT, va="top")
        y -= 0.16 * (wrapped.count("\n") + 1)
    fig.text(0.04, 0.025, "Generated by MTN Office tools from the uploaded data; every number is computed, not estimated. "
             "Check before sharing.", fontsize=7, color=GREY, fontfamily=FONT)
    png, pdf = io.BytesIO(), io.BytesIO()
    fig.savefig(png, format="png")
    fig.savefig(pdf, format="pdf")
    return png.getvalue(), pdf.getvalue()


def _wrap(text: str, width: int) -> str:
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n   ".join(lines[:3])


# -- dashboard (static HTML: no script, no external resources) --------------------------------------------------


def _esc(value) -> str:
    """HTML-escape, and encode '=' and ':' too, so text from the data can never look like an event
    handler or a javascript: link to LibreChat's static-HTML check (which would refuse the file)."""
    return html.escape(str(value)).replace("=", "&#61;").replace(":", "&#58;")


def dashboard_html(run: dict, title: str, insights: list[str], charts: dict[str, bytes]) -> bytes:
    esc = _esc
    tiles = "".join(
        f'<div class="tile"><div class="k">{esc(l)}</div><div class="v">{esc(v)}</div><div class="d">{esc(d)}</div></div>'
        for l, v, d in headlines(run)
    )
    sections = []
    for result in run.get("results", []):
        table = result.get("table", {})
        head = "".join(f"<th>{esc(str(c))}</th>" for c in table.get("columns", []))
        body = "".join("<tr>" + "".join(f"<td>{esc(_fmt(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else str(c))}</td>" for c in row) + "</tr>"
                       for row in table.get("rows", [])[:50])
        image = charts.get(result["id"])
        img = f'<img alt="{esc(result.get("title", ""))}" src="data:image/png;base64,{base64.b64encode(image).decode()}">' if image else ""
        note = f'<p class="note">{esc(result["note"])}</p>' if result.get("note") else ""
        sections.append(f'<section><h2>{esc(result.get("title", ""))}</h2>{img}<table><thead><tr>{head}</tr></thead>'
                        f'<tbody>{body}</tbody></table><p class="src">{esc(source_line(run, result))}</p>{note}</section>')
    items = "".join(f"<li>{esc(t)}</li>" for t in insights[:MAX_INSIGHTS]) or "<li>See the analysis results in the chat.</li>"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
body{{margin:0;font-family:"MTN Brighter Sans",Arial,sans-serif;color:{INK};background:#fff}}
header{{background:{YELLOW};padding:20px 28px}} header h1{{margin:0;font-size:24px}} header p{{margin:4px 0 0;font-size:13px}}
main{{max-width:1100px;margin:0 auto;padding:20px 24px 40px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}}
.tile{{background:#FFF5CC;border:2px solid {YELLOW};border-radius:12px;padding:12px 14px}}
.k{{font-size:12px;color:{GREY}}} .v{{font-size:26px;font-weight:700}} .d{{font-size:12px;color:{GREY}}}
section{{border:1px solid {LIGHT};border-radius:12px;padding:14px 16px;margin:14px 0}} h2{{font-size:17px;margin:0 0 8px}}
img{{max-width:100%;height:auto}} table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}}
th{{background:#111;color:{YELLOW};text-align:left;padding:6px 8px}} td{{border-bottom:1px solid {LIGHT};padding:5px 8px}}
.src,.note,footer{{font-size:12px;color:{GREY}}}
</style></head><body>
<header><h1>{esc(title)}</h1><p>{esc(str(run.get('file')))} · computed {esc(date.today().strftime('%d %B %Y'))} · MTN Internal</p></header>
<main><div class="tiles">{tiles}</div>
<section><h2>Key insights</h2><ul>{items}</ul></section>
{''.join(sections)}
<footer>Every number on this page was computed from the uploaded file by MTN Office tools (run {esc(str(run.get('run_id')))}); none is estimated. Check before sharing.</footer>
</main></body></html>
"""
    return page.encode("utf-8")


# -- PowerPoint and Excel specs (built by the existing, validated pipeline) ----------------------------------------


def _safe_text(value, limit: int) -> str:
    text = str(value)
    if text[:1] in ("=", "+", "-", "@") and not re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
        text = "'" + text
    return text[:limit]


def presentation_spec(run: dict, title: str, insights: list[str], filename: str) -> dict:
    slides = [{"title": "Key insights", "bullets": [_safe_text(t, 200) for t in (insights or ["See the analysis results in the chat."])[:6]]}]
    for result in chartable(run)[:6]:
        rows = result["table"]["rows"]
        kind = result["type"]
        if kind == "time_trend":
            rows, chart_type, values = rows[-12:], "line", [r[1] or 0 for r in rows[-12:]]
        elif kind == "period_change":
            rows, chart_type, values = rows[-12:], "column", [r[4] or 0 for r in rows[-12:]]
        else:
            rows, chart_type, values = rows[:12], ("bar" if kind != "distribution" else "column"), [r[1] or 0 for r in rows[:12]]
        series_name = (result["table"]["columns"][4] if kind == "period_change" else result["table"]["columns"][1])[:40]
        slides.append({
            "title": _safe_text(result.get("title", "Result"), 90),
            "chart": {"type": chart_type, "categories": [_safe_text(r[0], 30) or "–" for r in rows],
                      "series": [{"name": _safe_text(series_name, 40), "values": [float(v) for v in values]}]},
            "notes": source_line(run, result) + (". " + result["note"] if result.get("note") else ""),
        })
    notes = [f"File: {run.get('file')}"]
    for r in run.get("results", [])[:4]:
        left = r.get("rows_left_out")
        notes.append(f"{r.get('title', '')[:60]}: {r.get('rows_used', 0):,} rows used" + (f"; left out {sum(left.values())} blank" if left else ""))
    slides.append({"title": "About the data", "bullets": [_safe_text(n, 200) for n in notes[:6]]})
    return {"template": "executive_update", "title": _safe_text(title, 90), "subtitle": f"From {run.get('file')}"[:140],
            "slides": slides[:20], "filename": filename}


def _sheet_name(title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title)[:28].strip() or "Result"
    name, n = base, 2
    while name.lower() in used:
        name, n = f"{base[:25]} {n}", n + 1
    used.add(name.lower())
    return name


def workbook_spec(run: dict, title: str, insights: list[str], filename: str) -> dict:
    used: set[str] = {"summary"}
    summary_rows = [[_safe_text(l, 200), _safe_text(v, 200), _safe_text(d, 200)] for l, v, d in headlines(run)]
    summary_rows += [["Insight", _safe_text(t, 200), ""] for t in insights[:MAX_INSIGHTS]]
    summary_rows.append(["Source file", _safe_text(run.get("file"), 200), f"run {run.get('run_id')}"])
    sheets = [{"name": "Summary", "columns": [{"name": "Item"}, {"name": "Value"}, {"name": "Detail"}], "rows": summary_rows}]
    for result in chartable(run)[:5]:
        columns = result["table"]["columns"]
        rows = result["table"]["rows"][:2000]
        types = ["number" if isinstance(rows[0][i], (int, float)) and not isinstance(rows[0][i], bool) else "text" for i in range(len(columns))]
        kind = result["type"]
        value_col = columns[4] if kind == "period_change" else columns[1]
        sheets.append({
            "name": _sheet_name(result.get("title", "Result"), used),
            "columns": [{"name": _safe_text(c, 60), "type": t} for c, t in zip(columns, types)],
            "rows": [[(_safe_text(v, 200) if t == "text" and v is not None else v) for v, t in zip(row, types)] for row in rows],
            "chart": {"type": "line" if kind == "time_trend" else ("column" if kind in ("distribution", "period_change") else "bar"),
                      "title": _safe_text(result.get("title", ""), 80), "source": "data",
                      "category_column": _safe_text(columns[0], 60), "value_columns": [_safe_text(value_col, 60)]},
        })
    return {"template": "action_tracker", "title": _safe_text(title, 100), "sheets": sheets[:6], "filename": filename}
