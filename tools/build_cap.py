#!/usr/bin/env python3
"""Build docs/salary-cap.html (Nuggets salary-cap tracker) from tools/cap_data.json.

Data is hand-maintained (Spotrac cap table + multi-year page, cross-checked
against Basketball-Reference, Hoops Rumors and NBA.com). This script never
fetches or invents numbers: anything null renders as an em dash with a note.
ESPN player links are reused from docs/roster.html when present.

Usage: python3 tools/build_cap.py [--out docs/salary-cap.html] [--asof "Fri Oct 16, 2026 · 7:30 PM MDT"]
Exits non-zero if the standard-contract cap hits don't add up to Spotrac's
active-roster total stored in the data file (catches typos).
"""
import argparse, html, json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "..", "docs")
E = lambda s: html.escape(str(s), quote=True)
EXT = 'target="_blank" rel="noopener noreferrer"'
DASH = '<span class="unavail">—</span>'
OPT = {"PO": ("Player option", "cap-opt--po"), "TO": ("Team option", "cap-opt--to"),
       "ETO": ("Early termination option", "cap-opt--po"), "NG": ("Non-guaranteed", "cap-opt--ng")}


def money(n, sign=False):
    if n is None:
        return DASH
    s = f"${abs(n):,.0f}"
    if n < 0:
        return "−" + s
    return ("+" + s) if sign else s


def pct(n, cap):
    return f"{n / cap * 100:.2f}%" if n is not None else DASH


def espn_links():
    links = {}
    try:
        s = open(os.path.join(DOCS, "roster.html"), encoding="utf-8").read()
    except OSError:
        return links
    for href, name in re.findall(r'<a href="(https://www\.espn\.com/nba/player/[^"]+)"[^>]*>([^<]+)</a>', s):
        links[html.unescape(name).strip()] = href
    return links


def season_label(s):
    return s.replace("-", "–")


def build(d, asof):
    th = d["thresholds"]; tm = d["team"]; cap = th["salary_cap"]
    fut = d["future_seasons"]; fns = d["footnotes"]
    links = espn_links()
    std = [p for p in d["players"] if p["status"] == "standard"]
    tw = [p for p in d["players"] if p["status"] == "two-way"]
    e10 = [p for p in d["players"] if p["status"].startswith("camp")]
    active = sum(p["cap_hit"] for p in std)
    if active != tm["spotrac_active_total"]:
        sys.exit(f"DATA ERROR: standard cap hits sum to {active:,} but Spotrac active total is {tm['spotrac_active_total']:,}")
    dead = sum(x["amounts"].get(d["season"], 0) for x in d["dead_money"])
    cap_number = active + dead
    fn_order = []
    for p in std:
        fn_order += [k for k in [p.get("fn")] + [f.get("fn") for f in p["future"].values()] if k]
    fn_order += [k for k in fns if k not in fn_order]
    fn_num = {k: i + 1 for i, k in enumerate(dict.fromkeys(fn_order))}

    def sup(k):
        return f'<sup class="ros-fn"><a href="#fn-{k}">{fn_num[k]}</a></sup>' if k in fn_num else ""

    def name_cell(p, tag=""):
        disp = p.get("display", p["name"])
        href = links.get(disp) or links.get(p["name"])
        nm = f'<a href="{E(href)}" {EXT}>{E(disp)}</a>' if href else E(disp)
        flag = ' <span class="cap-flag">Deadline</span>' if p.get("flag") == "deadline" else ""
        return f'<td data-label="Player" class="ros-player">{nm}{tag}{flag}</td>'

    rows = []
    ncol = 7 + len(fut)
    rows.append(f'<tr class="ros-group"><th colspan="{ncol}" scope="colgroup">Standard contracts · {len(std)} of 15</th></tr>')
    totals = {s: 0 for s in fut}
    for p in std:
        cells = []
        for s in fut:
            f = p["future"].get(s)
            if not f:
                cells.append(f'<td data-label="{season_label(s)}" class="cap-num cap-empty"></td>')
                continue
            totals[s] += f["amount"]
            o = f.get("option")
            badge = f' <span class="cap-opt {OPT[o][1]}" title="{OPT[o][0]}">{o}</span>' if o else ""
            note = f'<span class="cap-sub">{E(f["note"])}</span>' if f.get("note") else ""
            cells.append(f'<td data-label="{season_label(s)}" class="cap-num">{money(f["amount"])}{sup(f.get("fn"))}{badge}{note}</td>')
        hit = money(p["cap_hit"]) + ('<sup class="ros-fn">*</sup>' if p.get("min") else "") + sup(p.get("fn"))
        rows.append(
            "<tr>" + name_cell(p) +
            f'<td data-label="Type" class="cap-text">{E(p["type"])}<span class="cap-sub">{E(p.get("signed", ""))}</span></td>'
            f'<td data-label="2026–27 cap hit" class="cap-num cap-hit">{hit}</td>'
            f'<td data-label="% of cap" class="cap-num">{pct(p["cap_hit"], cap)}</td>' + "".join(cells) +
            f'<td data-label="Guarantees" class="cap-text">{E(p["guarantee"])}</td>'
            f'<td data-label="How acquired" class="cap-text">{E(p["acquired"])}</td>'
            f'<td data-label="Status / next decision" class="cap-text">{E(p["status_note"])}</td></tr>')
    rows.append(
        f'<tr class="cap-total"><td data-label="Player" class="ros-player">Standard total</td><td data-label="Type" class="cap-text">{len(std)} players</td>'
        f'<td data-label="2026–27 cap hit" class="cap-num cap-hit">{money(active)}</td><td data-label="% of cap" class="cap-num">{pct(active, cap)}</td>' +
        "".join(f'<td data-label="{season_label(s)}" class="cap-num">{money(totals[s]) if totals[s] else ""}</td>' for s in fut) +
        '<td data-label="Guarantees" class="cap-text">Future totals include options</td><td class="cap-text cap-empty"></td><td class="cap-text cap-empty"></td></tr>')
    rows.append(f'<tr class="ros-group"><th colspan="{ncol}" scope="colgroup">Two-way contracts · {len(tw)} of 3 · no cap hit</th></tr>')
    for p in tw:
        rows.append(
            '<tr class="ros-two-way">' + name_cell(p, ' <span class="ros-tag ros-tag--tw">Two-way</span>') +
            f'<td data-label="Type" class="cap-text">Two-way · salary {money(p["salary"])}</td>'
            '<td data-label="2026–27 cap hit" class="cap-num"><span class="unavail">No cap hit</span></td>'
            '<td data-label="% of cap" class="cap-num cap-empty"></td>' +
            "".join(f'<td data-label="{season_label(s)}" class="cap-num cap-empty"></td>' for s in fut) +
            f'<td data-label="Guarantees" class="cap-text">{E(p["partial_guarantee"])}</td>'
            f'<td data-label="How acquired" class="cap-text">{E(p["acquired"])}</td>'
            f'<td data-label="Status / next decision" class="cap-text">{DASH if p["status_note"] == "—" else E(p["status_note"])}</td></tr>')
    if e10:
        rows.append(f'<tr class="ros-group"><th colspan="{ncol}" scope="colgroup">Exhibit 10 camp deals · {len(e10)} · non-guaranteed</th></tr>')
    for p in e10:
        rows.append(
            '<tr class="ros-camp-e10">' + name_cell(p, ' <span class="ros-tag ros-tag--camp">Exhibit 10</span>') +
            '<td data-label="Type" class="cap-text">Exhibit 10 (1-yr minimum)</td>'
            f'<td data-label="2026–27 cap hit" class="cap-num">{DASH}<sup class="ros-fn">†</sup></td>'
            '<td data-label="% of cap" class="cap-num cap-empty"></td>' +
            "".join(f'<td data-label="{season_label(s)}" class="cap-num cap-empty"></td>' for s in fut) +
            '<td data-label="Guarantees" class="cap-text">Non-guaranteed</td>'
            f'<td data-label="How acquired" class="cap-text">{E(p["acquired"])}</td>'
            '<td data-label="Status / next decision" class="cap-text">Waive by Oct 17 for no cap charge</td></tr>')

    fn_html = "".join(f'<li id="fn-{k}">{E(fns[k])}</li>' for k in fn_num)

    # Thresholds table
    trows = []
    for label, amt, used, uname in [
        ("Minimum team salary", th["minimum_team_salary"], cap_number, "cap number"),
        ("Salary cap", cap, cap_number, "cap number"),
        ("Luxury tax line", th["luxury_tax"], tm["tax_salary"], "tax salary"),
        ("First apron", th["first_apron"], tm["apron_salary"], "apron salary"),
        ("Second apron", th["second_apron"], tm["apron_salary"], "apron salary"),
    ]:
        diff = used - amt
        if label.startswith("Minimum"):
            res = f'<span class="cap-under">{money(diff)} above the floor</span>'
        else:
            res = f'<span class="cap-over">{money(diff)} over</span>' if diff > 0 else f'<span class="cap-under">{money(-diff)} under</span>'
        trows.append(f'<tr><td data-label="Threshold">{label}</td><td data-label="2026–27 level" class="cap-num">{money(amt)}</td>'
                     f'<td data-label="Denver figure" class="cap-num">{money(used)} <span class="cap-sub-inline">({uname})</span></td><td data-label="Denver vs. line" class="cap-num">{res}</td></tr>')

    dead_rows = "".join(
        f'<tr><td data-label="Player">{E(x["name"])}</td>' +
        "".join(f'<td data-label="{season_label(s)}" class="cap-num">{money(x["amounts"].get(s)) if x["amounts"].get(s) else ""}</td>' for s in [d["season"]] + fut[:2]) +
        f'<td data-label="Note" class="cap-text">{E(x["note"])}</td></tr>' for x in d["dead_money"])
    waived = "".join(f'<li><strong>{E(x["name"])}</strong>: {E(x["note"])}</li>' for x in d["waived_no_charge"])
    exc = "".join(f'<tr><td data-label="Exception" class="cap-text">{E(x["type"])}</td><td data-label="Amount" class="cap-num">{money(x["amount"])}</td>'
                  f'<td data-label="Status" class="cap-text">{E(x["status"])}</td><td data-label="Source" class="cap-text">{E(x["src"])}</td></tr>' for x in d["exceptions"])
    picks = "".join(f"<li>{E(x)}</li>" for x in d["picks"])
    dates = "".join(f'<div><dt>{E(x["date"])}</dt><dd>{E(x["text"])}</dd></div>' for x in d["key_dates"])
    est = " · ".join(f'{money(x["amount"])} ({E(x["source"])})' for x in tm["tax_bill_estimates"])
    srcs = " ".join(f'<a href="{E(u)}" {EXT}>{E(t)}</a>' for t, u in d["sources"])
    min_note = next((p for p in std if p.get("min")), None)

    deck = (f"Denver is {money(tm['apron_salary'] - th['second_apron'])} over the second apron and {money(tm['tax_salary'] - th['luxury_tax'])} over the luxury tax line. "
            f"{len(std)} standard contracts count {money(active)}, plus {money(dead)} in dead money. Two-way and Exhibit 10 deals don't count against the cap.")

    return TEMPLATE.format(
        DECK=deck, ASOF=E(asof), CAP_NUMBER=money(cap_number), TAX=money(tm["tax_salary"]), APRON=money(tm["apron_salary"]),
        OVER2=money(tm["apron_salary"] - th["second_apron"]), OVERTAX=money(tm["tax_salary"] - th["luxury_tax"]),
        OVERCAP=money(cap_number - cap), STD=len(std), TW=len(tw), E10=len(e10), TOTAL=len(std) + len(tw) + len(e10),
        ACTIVE=money(active), DEAD=money(dead), TROWS="".join(trows),
        TAXGAP=money(tm["tax_salary"] - cap_number), APGAP=money(tm["apron_salary"] - tm["tax_salary"]),
        HR_TAX=E(tm["hoopsrumors_tax_salary_rounded"]), HR_AP=E(tm["hoopsrumors_apron_salary_rounded"]),
        EST=est, FUTH="".join(f'<th scope="col">{season_label(s)}</th>' for s in fut),
        ROWS="\n".join(rows), FNS=fn_html,
        MINSAL=money(min_note["cap_hit"]) if min_note else "",
        DEADH="".join(f'<th scope="col">{season_label(s)}</th>' for s in [d["season"]] + fut[:2]),
        DEAD_ROWS=dead_rows, WAIVED=waived, HOLDS_TOTAL=money(d["cap_holds"]["total"]), HOLDS_ITEMS=E(d["cap_holds"]["items"]),
        HOLDS_NOTE=E(d["cap_holds"]["note"]), SPOT_ALLOC=money(tm["spotrac_total_cap_allocations"]),
        EXC=exc, PICKS=picks, DATES=dates, SRCS=srcs, TMLE=money(th["taxpayer_mle"]),
        CHECKED=E(datetime.fromisoformat(d["checked"]).astimezone(MT).strftime("%a %b %-d, %Y · %-I:%M %p %Z")))


TEMPLATE = open(os.path.join(HERE, "cap_template.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "cap_template.html")) else None


def main():
    global TEMPLATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "cap_data.json"))
    ap.add_argument("--out", default=os.path.join(DOCS, "salary-cap.html"))
    ap.add_argument("--asof", default=None, help="As-of label; defaults to the data file's 'checked' time in MT")
    a = ap.parse_args()
    if TEMPLATE is None:
        sys.exit("TEMPLATE ERROR: tools/cap_template.html missing")
    d = json.load(open(a.data, encoding="utf-8"))
    asof = a.asof or datetime.fromisoformat(d["checked"]).astimezone(MT).strftime("%a %b %-d, %Y · %-I:%M %p %Z")
    out = build(d, asof)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
