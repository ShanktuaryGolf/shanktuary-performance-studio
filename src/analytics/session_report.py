"""Session report export: CSV for analysis, PDF for sharing.

Pure functions over the stored session dict -- no Tk, no server, no file
reads beyond what the caller passes in. The PDF is built from Pillow-rendered
pages wrapped in a minimal hand-written PDF container so the app gains no
new dependency (reportlab is not in requirements.txt and CI packages with
PyInstaller from exactly that list).

Data honesty carries through: absent fields are BLANK, never 0; suspect
shots are flagged in the rows and excluded from the per-club summary; the
"Nova measures ball flight, not face contact" line is on the summary page.
"""
from __future__ import annotations

import csv
import io
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

MPS_TO_MPH = 2.23694

# Column order is part of the contract: people build spreadsheets on it.
COLUMNS = [
    "shot", "time", "club", "shot_name",
    "ball_speed_mph", "club_speed_mph", "smash",
    "launch_deg", "hla_deg", "spin_rpm", "spin_axis_deg",
    "carry_yds", "total_yds", "offline_yds", "apex_ft",
    "club_path_deg", "face_to_path_deg", "face_to_target_deg",
    "ball", "marked_contact_h_mm", "marked_contact_v_mm",
    "flag", "timestamp_ns",
]


def _num(value) -> float | None:
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _handed(value, is_left_handed: bool):
    if isinstance(value, dict):
        key = "left_handed" if is_left_handed else "right_handed"
        return value.get(key, value.get("right_handed"))
    return value


def _blank(v, digits=1):
    return "" if v is None else round(v, digits)


def shot_rows(session: dict[str, Any], is_left_handed: bool = False) -> list[dict[str, Any]]:
    """One flat row per shot; absent fields blank, handed fields resolved."""
    rows = []
    for i, s in enumerate(session.get("shots") or [], start=1):
        if not isinstance(s, dict):
            continue
        ogc = s.get("open_golf_coach") or {}
        us = ogc.get("us_customary_units") or {}
        bs = _num(us.get("ball_speed_mph"))
        if bs is None:
            mps = _num(s.get("ball_speed_meters_per_second"))
            bs = mps * MPS_TO_MPH if mps is not None else None
        cs = _num(us.get("club_speed_mph"))
        if cs is None:
            mps = _num(ogc.get("club_speed_meters_per_second"))
            cs = mps * MPS_TO_MPH if mps is not None else None
        quality = s.get("_data_quality") or {}
        flag = ""
        if isinstance(quality, dict) and quality.get("suspect"):
            flag = "suspect: " + "; ".join(str(x) for x in quality.get("issues") or []) or "suspect"
        elif s.get("excluded"):
            flag = "excluded"
        elif s.get("_demo") or s.get("_source") == "demo":
            flag = "demo"
        name = _handed(ogc.get("shot_name"), is_left_handed)
        rows.append({
            "shot": s.get("shot_number") or i,
            "time": s.get("timestamp") or "",
            "club": s.get("club") or "",
            "shot_name": "" if name is None else str(name),
            "ball_speed_mph": _blank(bs),
            "club_speed_mph": _blank(cs),
            "smash": _blank(_num(ogc.get("smash_factor")), 3),
            "launch_deg": _blank(_num(s.get("vertical_launch_angle_degrees"))),
            "hla_deg": _blank(_num(s.get("horizontal_launch_angle_degrees"))),
            "spin_rpm": ("" if _num(s.get("total_spin_rpm")) is None else int(round(_num(s.get("total_spin_rpm"))))),
            "spin_axis_deg": _blank(_num(s.get("spin_axis_degrees"))),
            "carry_yds": _blank(_num(us.get("carry_distance_yards"))),
            "total_yds": _blank(_num(us.get("total_distance_yards"))),
            "offline_yds": _blank(_num(us.get("offline_distance_yards"))),
            "apex_ft": _blank(_num(us.get("apex_height_feet")), 0),
            "club_path_deg": _blank(_num(_handed(ogc.get("club_path_degrees"), is_left_handed))),
            "face_to_path_deg": _blank(_num(_handed(ogc.get("club_face_to_path_degrees"), is_left_handed))),
            "face_to_target_deg": _blank(_num(_handed(ogc.get("club_face_to_target_degrees"), is_left_handed))),
            "ball": s.get("ball") or "",
            # The golfer's own contact mark (training label), +heel / +high.
            "marked_contact_h_mm": _blank(_num((s.get("marked_contact") or {}).get("horizontal_mm")) if isinstance(s.get("marked_contact"), dict) else None),
            "marked_contact_v_mm": _blank(_num((s.get("marked_contact") or {}).get("vertical_mm")) if isinstance(s.get("marked_contact"), dict) else None),
            "flag": flag,
            "timestamp_ns": s.get("timestamp_ns") or "",
        })
    return rows


def club_summary(session: dict[str, Any], is_left_handed: bool = False) -> list[dict[str, Any]]:
    """Per-club averages over clean FULL swings only.

    Flagged rows are excluded, and so are partial swings/misreads, through the
    same gate the Shanktuary Index scores against (`valid_shots`): a real
    session file had 59 of 142 seven-irons under 20 yds -- tops and practice
    swings the device registered -- and averaging those in made the club read
    41 yds. The table says how many were left out.
    """
    from .index import valid_shots

    shots = [s for s in session.get("shots") or [] if isinstance(s, dict)]
    kept = {id(s) for s in valid_shots(shots)}
    rows = shot_rows(session, is_left_handed)
    by_club: dict[str, list[dict]] = {}
    for s, r in zip(shots, rows):
        if r["flag"] or not r["club"] or id(s) not in kept:
            continue
        by_club.setdefault(r["club"], []).append(r)
    out = []
    for club, rows in by_club.items():
        def col(key):
            return [r[key] for r in rows if r[key] != ""]
        carries, offs, bss, spins, launches = (col(k) for k in
                                               ("carry_yds", "offline_yds", "ball_speed_mph", "spin_rpm", "launch_deg"))
        out.append({
            "club": club,
            "shots": len(rows),
            "avg_carry_yds": round(statistics.mean(carries), 1) if carries else "",
            "carry_sd_yds": round(statistics.pstdev(carries), 1) if len(carries) > 1 else "",
            "avg_offline_yds": round(statistics.mean(offs), 1) if offs else "",
            "avg_ball_speed_mph": round(statistics.mean(bss), 1) if bss else "",
            "avg_spin_rpm": round(statistics.mean(spins)) if spins else "",
            "avg_launch_deg": round(statistics.mean(launches), 1) if launches else "",
        })
    out.sort(key=lambda c: -(c["avg_carry_yds"] or 0))
    return out


def excluded_count(session: dict[str, Any], is_left_handed: bool = False) -> dict[str, int]:
    """How many shots the summary left out, and why."""
    from .index import valid_shots

    shots = [s for s in session.get("shots") or [] if isinstance(s, dict)]
    rows = shot_rows(session, is_left_handed)
    flagged = sum(1 for r in rows if r["flag"])
    kept = {id(s) for s in valid_shots(shots)}
    partial = sum(1 for s, r in zip(shots, rows) if not r["flag"] and id(s) not in kept)
    return {"flagged": flagged, "partial_or_misread": partial}


def default_filename(session: dict[str, Any], ext: str) -> str:
    day = str(session.get("created_at") or datetime.now().strftime("%Y-%m-%d"))[:10]
    name = re.sub(r"[^A-Za-z0-9]+", "-", str(session.get("name") or "session")).strip("-")
    return f"shanktuary_{day}_{name}.{ext}"


def write_csv(session: dict[str, Any], path: Path | str, is_left_handed: bool = False) -> Path:
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in shot_rows(session, is_left_handed):
            w.writerow(row)
    return path


# --- PDF -------------------------------------------------------------------

PAGE_W, PAGE_H = 1240, 1754  # A4 at 150 dpi
_MARGIN = 70
_BG = (9, 27, 36)
_TEXT = (243, 246, 250)
_TEXT_2 = (179, 190, 194)
_TEXT_3 = (112, 134, 140)
_GOLD = (212, 162, 79)
_TEAL = (120, 196, 193)
_HAIR = (42, 76, 85)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
        "C:/Windows/Fonts/%s" % ("arialbd.ttf" if bold else "arial.ttf"),
        "/System/Library/Fonts/Supplemental/Arial%s.ttf" % (" Bold" if bold else ""),
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


class _Page:
    """A Pillow page that remembers every string it drew (for tests)."""

    def __init__(self):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (PAGE_W, PAGE_H), _BG)
        self.d = ImageDraw.Draw(self.img)
        self.drawn: list[str] = []
        self.placed: list[tuple] = []   # (x, y, w, h, s) as actually drawn
        self.y = _MARGIN

    def text(self, x, y, s, size=22, color=_TEXT_2, bold=False, anchor="la"):
        f = _font(size, bold)
        self.d.text((x, y), s, fill=color, font=f, anchor=anchor)
        self.drawn.append(s)
        l, t, r, b = self.d.textbbox((x, y), s, font=f, anchor=anchor)
        self.placed.append((l, t, r - l, b - t, s))
        return b - t

    def line(self, y):
        self.d.line((_MARGIN, y, PAGE_W - _MARGIN, y), fill=_HAIR, width=2)


def _debug_drawn_text(page: _Page) -> list[str]:
    return list(page.drawn)


def render_summary_page(session, index_result=None, index_trend=None, is_left_handed=False) -> _Page:
    p = _Page()
    y = p.y
    p.text(_MARGIN, y, "SHANKTUARY PERFORMANCE STUDIO", 20, _GOLD, True); y += 34
    p.text(_MARGIN, y, str(session.get("name") or "Session"), 40, _TEXT, True); y += 56
    created = str(session.get("created_at") or "")
    shots = [s for s in session.get("shots") or [] if isinstance(s, dict)]
    p.text(_MARGIN, y, f"{created}   ·   {len(shots)} shots", 22, _TEXT_3); y += 40
    notes = str(session.get("notes") or "").strip()
    if notes:
        p.text(_MARGIN, y, "Notes: " + notes[:140], 20, _TEXT_2); y += 34
    p.line(y); y += 24

    # Index block
    p.text(_MARGIN, y, "PROGRESS", 18, _TEXT_3); y += 30
    if index_result and index_result.get("status") == "available":
        p.text(_MARGIN, y, f"Shanktuary Index {float(index_result['score']):.1f}", 34, _GOLD, True); y += 46
        if index_trend and index_trend.get("delta") is not None:
            d = float(index_trend["delta"])
            p.text(_MARGIN, y, f"{d:+.1f} vs last snapshot", 22, _TEAL if d >= 0 else _TEXT_2, True)
            p.text(_MARGIN + 330, y, f"best {float(index_trend['best']):.1f} on {str(index_trend.get('best_at', ''))[:10]}",
                   20, _TEXT_3); y += 32
    else:
        reason = (index_result or {}).get("reason") or "Index needs more established clubs"
        p.text(_MARGIN, y, f"Shanktuary Index: {reason}", 20, _TEXT_3); y += 32
    y += 10
    p.line(y); y += 24

    # Per-club table
    p.text(_MARGIN, y, "PER CLUB (clean shots only)", 18, _TEXT_3); y += 30
    cols = [("Club", 0), ("Shots", 240), ("Carry", 350), ("±SD", 480), ("Offline", 600),
            ("Ball mph", 730), ("Spin", 870), ("Launch", 990)]
    for label, dx in cols:
        p.text(_MARGIN + dx, y, label, 18, _TEXT_3)
    y += 28
    summary = club_summary(session, is_left_handed)
    for c in summary:
        vals = [c["club"], str(c["shots"]), f"{c['avg_carry_yds']}" if c["avg_carry_yds"] != "" else "—",
                f"{c['carry_sd_yds']}" if c["carry_sd_yds"] != "" else "—",
                f"{c['avg_offline_yds']:+.1f}" if c["avg_offline_yds"] != "" else "—",
                f"{c['avg_ball_speed_mph']}" if c["avg_ball_speed_mph"] != "" else "—",
                f"{c['avg_spin_rpm']}" if c["avg_spin_rpm"] != "" else "—",
                f"{c['avg_launch_deg']}" if c["avg_launch_deg"] != "" else "—"]
        row = "  ".join(vals)
        for (label, dx), v in zip(cols, vals):
            p.text(_MARGIN + dx, y, v, 20, _TEXT if label == "Club" else _TEXT_2)
        p.drawn.append(row)
        y += 30
        if y > PAGE_H - 260:
            break
    if not summary:
        p.text(_MARGIN, y, "No clean shots in this session", 20, _TEXT_3); y += 30
    ex = excluded_count(session, is_left_handed)
    if ex["flagged"] or ex["partial_or_misread"]:
        y += 8
        parts = []
        if ex["flagged"]:
            parts.append(f"{ex['flagged']} flagged suspect/excluded")
        if ex["partial_or_misread"]:
            parts.append(f"{ex['partial_or_misread']} partial swings or misreads (below the full-swing floor)")
        p.text(_MARGIN, y, "Left out of the averages: " + "; ".join(parts), 18, _TEXT_3); y += 28

    # Dispersion plot: offline (x) vs carry (y), clean shots, one colour per club.
    y += 14
    p.line(y); y += 24
    p.text(_MARGIN, y, "DISPERSION  (offline yds → , carry yds ↑)", 18, _TEXT_3); y += 26
    top = y
    bottom = PAGE_H - 150
    left, right = _MARGIN + 60, PAGE_W - _MARGIN - 20
    from .index import valid_shots as _valid
    _shots = [s for s in session.get("shots") or [] if isinstance(s, dict)]
    _kept = {id(s) for s in _valid(_shots)}
    rows = [r for s, r in zip(_shots, shot_rows(session, is_left_handed))
            if not r["flag"] and id(s) in _kept and r["carry_yds"] != "" and r["offline_yds"] != ""]
    if rows and bottom - top > 100:
        carries = [r["carry_yds"] for r in rows]
        offs = [r["offline_yds"] for r in rows]
        cmin, cmax = min(carries), max(carries)
        cpad = max(5.0, (cmax - cmin) * 0.1)
        cmin, cmax = cmin - cpad, cmax + cpad
        omax = max(10.0, max(abs(o) for o in offs) * 1.15)
        p.d.rectangle((left, top, right, bottom), outline=_HAIR, width=2)
        tx = (left + right) / 2
        p.d.line((tx, top, tx, bottom), fill=_HAIR, width=1)
        for frac in (0.25, 0.5, 0.75):
            gy = bottom - (bottom - top) * frac
            p.d.line((left, gy, right, gy), fill=_HAIR, width=1)
            p.text(left - 8, gy, f"{cmin + (cmax - cmin) * frac:.0f}", 16, _TEXT_3, anchor="rm")
        p.text(left, bottom + 6, f"{-omax:.0f}", 16, _TEXT_3)
        p.text(right, bottom + 6, f"{omax:.0f}", 16, _TEXT_3, anchor="ra")
        palette = [_GOLD, _TEAL, (163, 201, 120), (232, 140, 140), (200, 170, 230), (240, 200, 120)]
        clubs = list(dict.fromkeys(r["club"] for r in rows))
        for r in rows:
            col = palette[clubs.index(r["club"]) % len(palette)]
            px = tx + (r["offline_yds"] / omax) * (right - left) / 2
            py = bottom - (r["carry_yds"] - cmin) / (cmax - cmin) * (bottom - top)
            p.d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=col)
        lx = left
        for i, club in enumerate(clubs):
            col = palette[i % len(palette)]
            p.d.ellipse((lx, bottom + 34, lx + 12, bottom + 46), fill=col)
            p.text(lx + 18, bottom + 30, club, 16, _TEXT_2)
            lx += 160
    else:
        p.text(left, top + 20, "No plottable shots", 18, _TEXT_3)

    p.text(_MARGIN, PAGE_H - 60, "Nova measures ball flight, not face contact. Club speed and smash are model-derived.", 16, _TEXT_3)
    p.text(PAGE_W - _MARGIN, PAGE_H - 60, datetime.now().strftime("Generated %Y-%m-%d %H:%M"), 16, _TEXT_3, anchor="ra")
    return p


def render_shot_pages(session, is_left_handed=False) -> list[_Page]:
    """Dense shot table, paginated."""
    rows = shot_rows(session, is_left_handed)
    cols = [("#", "shot", 0), ("Time", "time", 55), ("Club", "club", 150), ("Shape", "shot_name", 250),
            ("Ball", "ball_speed_mph", 420), ("Launch", "launch_deg", 500), ("Spin", "spin_rpm", 585),
            ("Axis", "spin_axis_deg", 665), ("Carry", "carry_yds", 745), ("Total", "total_yds", 830),
            ("Offline", "offline_yds", 915), ("Flag", "flag", 1000)]
    flag_budget = PAGE_W - _MARGIN * 2 - 1000
    pages: list[_Page] = []
    per_page = 50
    for start in range(0, max(1, len(rows)), per_page):
        p = _Page()
        y = _MARGIN
        p.text(_MARGIN, y, f"{session.get('name') or 'Session'} — shots {start + 1}–{min(start + per_page, len(rows))} of {len(rows)}", 24, _TEXT, True)
        y += 44
        for label, _, dx in cols:
            p.text(_MARGIN + dx, y, label, 16, _TEXT_3)
        y += 24
        p.line(y); y += 8
        for r in rows[start:start + per_page]:
            for _, key, dx in cols:
                v = r[key]
                s = "" if v == "" else str(v)
                if key == "shot_name":
                    s = s[:18]
                if key == "flag" and s:
                    # "suspect: negative total_spin_rpm (-471)" -> "suspect" + fits.
                    s = s.split(":")[0]
                    f = _font(16)
                    while s and f.getlength(s) > flag_budget:
                        s = s[:-1]
                p.text(_MARGIN + dx, y, s, 16, _TEXT_2 if key != "flag" else _GOLD)
            y += 30
        pages.append(p)
    return pages


def _pdf_from_pages(pages: list[_Page]) -> bytes:
    """Minimal PDF: one DCT (JPEG) image per page, no external deps."""
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    page_ids = []
    kids_placeholder = add(b"")  # pages tree, filled in later
    for p in pages:
        buf = io.BytesIO()
        p.img.save(buf, format="JPEG", quality=88)
        jpg = buf.getvalue()
        img_id = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (PAGE_W, PAGE_H, len(jpg)) + jpg + b"\nendstream")
        # 595x842 pt = A4
        content = b"q 595 0 0 842 0 0 cm /Im0 Do Q"
        content_id = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page_id = add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>" % (kids_placeholder, img_id, content_id))
        page_ids.append(page_id)
    objs[kids_placeholder - 1] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (
        len(page_ids), b" ".join(b"%d 0 R" % i for i in page_ids))
    catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % kids_placeholder)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog_id, xref))
    return out.getvalue()


def write_pdf(session, path, index_result=None, index_trend=None, is_left_handed=False) -> Path:
    pages = [render_summary_page(session, index_result, index_trend, is_left_handed)]
    pages += render_shot_pages(session, is_left_handed)
    path = Path(path)
    path.write_bytes(_pdf_from_pages(pages))
    return path


__all__ = ["COLUMNS", "shot_rows", "club_summary", "default_filename", "write_csv",
           "write_pdf", "render_summary_page", "render_shot_pages"]
