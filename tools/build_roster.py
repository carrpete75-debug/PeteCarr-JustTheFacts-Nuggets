#!/usr/bin/env python3
"""Build docs/roster.html (current Nuggets roster) from live data.

Data:
  * ESPN site API team 7 roster  -> player list, jersey #, position, height,
    weight, age, college, ESPN player-card link (primary source).
  * ESPN site API NBA injuries   -> current injury tag (Denver entries only).
  * nba.com/nuggets/roster (__NEXT_DATA__) -> cross-check of the player list,
    experience (NBA seasons, "R" = rookie), jersey # cross-check, coaching staff.
  * tools/roster_contracts.json (hand-maintained from Spotrac, checked against
    Basketball-Reference) -> two-way / camp status and 2026-27 cap hits.
Never guesses: missing values render as <span class="unavail">.

Usage: python3 tools/build_roster.py [--out docs/roster.html]
Writes a fact pack to /workspace/nuggets-data/roster-YYYY-MM-DD.json and
exits non-zero if ESPN and nba.com player lists disagree (use --allow-mismatch
to publish anyway; mismatches are listed on the page).
"""
import argparse, html, json, os, re, subprocess, sys, unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
ESPN_ROSTER = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/7/roster"
ESPN_INJ = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
NBA_ROSTER = "https://www.nba.com/nuggets/roster"
E = lambda s: html.escape(str(s), quote=True)
EXT = 'target="_blank" rel="noopener noreferrer"'


def get(url, timeout=40, ua=True):
    # ESPN's site API rejects some browser UAs; call it with curl's default UA.
    return subprocess.run(["curl", "-sSL", "--fail", "--max-time", str(timeout)] + (["-A", UA] if ua else []) + [url],
                          capture_output=True, text=True, check=True).stdout


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+(ii|iii|iv|jr|sr)$", "", s).strip()


def mt(dt):
    s = dt.astimezone(MT).strftime("%a %b %-d, %Y · %-I:%M %p %Z")
    return s


def jersey_key(j):
    if j in (None, ""):
        return 999
    return -1 if j == "00" else int(j)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "roster.html"))
    ap.add_argument("--allow-mismatch", action="store_true")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)

    espn = json.loads(get(ESPN_ROSTER, ua=False))
    inj = json.loads(get(ESPN_INJ, ua=False))
    # nba.com sometimes serves rosterData={"error":...}; retry with a cache-buster.
    import time
    for attempt in range(6):
        nba_html = get(NBA_ROSTER + (f"?r={int(time.time())}{attempt}" if attempt else ""))
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', nba_html, re.S)
        nba = json.loads(m.group(1))["props"]["pageProps"]["rosterData"]
        if isinstance(nba, dict) and "roster" in nba:
            break
        time.sleep(5)
    else:
        sys.exit("NBA.COM ERROR: rosterData has no roster after retries: " + str(nba)[:200])
    contracts = json.load(open(os.path.join(HERE, "roster_contracts.json")))
    cmap = {norm(k): v for k, v in contracts["players"].items()}

    nba_by = {norm(p["name"]): p for p in nba["roster"]}
    den_inj = {}
    for t in inj.get("injuries", []):
        if t.get("id") == "7" or "Denver" in t.get("displayName", ""):
            for i in t.get("injuries", []):
                den_inj[norm(i["athlete"]["displayName"])] = i

    players, issues = [], []
    for p in espn["athletes"]:
        k = norm(p["displayName"])
        n = nba_by.get(k)
        c = cmap.get(k)
        link = next((l["href"] for l in p.get("links", []) if "playercard" in l.get("rel", [])), None)
        if not n:
            issues.append(f'{p["displayName"]} is on ESPN\'s roster but not nba.com\'s')
        if not c:
            issues.append(f'{p["displayName"]} has no entry in roster_contracts.json')
        exp = n["experience"] if n and n.get("experience") not in (None, "") else None
        if exp is None and p.get("experience") is not None:
            exp = str(p["experience"]["years"]) if p["experience"]["years"] else "R"
        ij = den_inj.get(k)
        players.append({
            "id": p["id"], "name": p["displayName"], "link": link,
            "jersey": p.get("jersey") or "", "nba_jersey": (n or {}).get("number") or "",
            "pos": p["position"]["abbreviation"], "pos_name": p["position"]["displayName"],
            "ht": p.get("displayHeight"), "wt": p.get("displayWeight"), "age": p.get("age"),
            "exp": exp, "college": (p.get("college") or {}).get("name") or (c or {}).get("pre_draft"),
            "status": (c or {}).get("status", "unknown"), "cap_hit": (c or {}).get("cap_hit"),
            "min": (c or {}).get("min", False), "base": (c or {}).get("base"), "cnote": (c or {}).get("note"),
            "injury": {"status": ij["status"], "date": ij.get("date"), "short": ij.get("shortComment")} if ij else None,
        })
    espn_keys = {norm(p["displayName"]) for p in espn["athletes"]}
    for k, n in nba_by.items():
        if k not in espn_keys:
            issues.append(f'{n["name"]} is on nba.com\'s roster but not ESPN\'s')
    if issues and not a.allow_mismatch:
        print("ROSTER MISMATCH:\n  " + "\n  ".join(issues), file=sys.stderr)
        sys.exit(2)

    order = {"G": 0, "F": 1, "C": 2}
    players.sort(key=lambda r: (order.get(r["pos"], 3), jersey_key(r["jersey"]), r["name"]))
    groups = [("G", "Guards"), ("F", "Forwards"), ("C", "Centers")]
    counts = {s: sum(1 for p in players if p["status"] == s) for s in ("standard", "two-way", "camp-e10", "camp")}

    fn_rows = []
    def row(p):
        badges = ""
        if p["status"] == "two-way":
            badges += ' <span class="ros-tag ros-tag--tw">Two-way</span>'
        elif p["status"] == "camp-e10":
            badges += ' <span class="ros-tag ros-tag--camp">Exhibit 10</span>'
        elif p["status"] == "camp":
            badges += ' <span class="ros-tag ros-tag--camp">Camp deal</span>'
        if p["injury"]:
            d = datetime.fromisoformat(p["injury"]["date"].replace("Z", "+00:00")).astimezone(MT)
            title = f'ESPN injury report, updated {d:%b %-d, %Y}'
            badges += f' <span class="ros-inj" title="{E(title)}">{E(p["injury"]["status"])} · {d:%b %-d}</span>'
        num = E(p["jersey"]) if p["jersey"] else '<span class="unavail">—</span>'
        if p["nba_jersey"] and p["jersey"] and p["nba_jersey"] != p["jersey"]:
            num += '<sup class="ros-fn">†</sup>'
            fn_rows.append(f'{p["name"]} #{p["nba_jersey"]}')
        name = f'<a href="{E(p["link"])}" {EXT}>{E(p["name"])}</a>' if p["link"] else E(p["name"])
        if p["cap_hit"]:
            cap = f'${p["cap_hit"]:,}' + ('<sup class="ros-fn">*</sup>' if p["min"] or p["cnote"] else "")
        elif p["status"] == "two-way":
            cap = '<span class="unavail">Two-way (no cap hit)</span>'
        elif p["status"] in ("camp", "camp-e10"):
            cap = '<span class="unavail">Non-guaranteed</span>'
        else:
            cap = '<span class="unavail">n/a</span>'
        exp = "Rookie" if p["exp"] == "R" else (E(p["exp"]) if p["exp"] is not None else '<span class="unavail">—</span>')
        col = E(p["college"]) if p["college"] else '<span class="unavail">—</span>'
        cls = f' class="ros-{p["status"]}"' if p["status"] != "standard" else ""
        return (f'        <tr{cls}><td data-label="#" class="ros-num">{num}</td>'
                f'<td data-label="Player" class="ros-player">{name}{badges}</td>'
                f'<td data-label="Pos" class="ros-stat">{E(p["pos"])}</td><td data-label="Ht" class="ros-stat">{E(p["ht"] or "—")}</td>'
                f'<td data-label="Wt" class="ros-stat">{E((p["wt"] or "—").replace(" lbs", " lb"))}</td><td data-label="Age" class="ros-stat">{E(p["age"] if p["age"] is not None else "—")}</td>'
                f'<td data-label="Exp" class="ros-stat">{exp}</td><td data-label="College / pre-draft" class="ros-wide">{col}</td>'
                f'<td data-label="2026–27 cap hit" class="ros-cap ros-wide">{cap}</td></tr>')

    body = []
    for code, label in groups:
        g = [p for p in players if p["pos"] == code]
        if not g:
            continue
        body.append(f'        <tr class="ros-group"><th colspan="9" scope="colgroup">{label} · {len(g)}</th></tr>')
        body += [row(p) for p in g]
    other = [p for p in players if p["pos"] not in order]
    if other:
        body.append(f'        <tr class="ros-group"><th colspan="9" scope="colgroup">Other · {len(other)}</th></tr>')
        body += [row(p) for p in other]

    # Coaches / staff (nba.com), head coach cross-checked with ESPN
    coaches = nba.get("coaches") or []
    espn_hc = " ".join(filter(None, [(espn.get("coach") or [{}])[0].get("firstName"), (espn.get("coach") or [{}])[0].get("lastName")]))
    staff_types = {}
    for c in coaches:
        staff_types.setdefault(c["type"], []).append(c["displayName"])
    staff_html = []
    for t in ["Head Coach", "Assistant Coach", "Trainer"] + [t for t in staff_types if t not in ("Head Coach", "Assistant Coach", "Trainer")]:
        if t in staff_types:
            lbl = t + ("s" if len(staff_types[t]) > 1 else "")
            staff_html.append(f'<div><dt>{E(lbl)}</dt><dd>{E(", ".join(staff_types[t]))}</dd></div>')
    if not staff_html and espn_hc:
        staff_html.append(f'<div><dt>Head Coach</dt><dd>{E(espn_hc)}</dd></div>')

    inj_list = [p for p in players if p["injury"]]
    if inj_list:
        items = []
        for p in inj_list:
            d = datetime.fromisoformat(p["injury"]["date"].replace("Z", "+00:00")).astimezone(MT)
            items.append(f'<li><strong>{E(p["name"])}</strong>: {E(p["injury"]["status"])} (ESPN, last updated {d:%b %-d, %Y}). {E(p["injury"]["short"] or "")}</li>')
        inj_html = '<ul class="ros-injuries">' + "".join(items) + "</ul>"
    else:
        inj_html = '<p><span class="unavail">ESPN lists no Nuggets injuries right now.</span></p>'

    notes = []
    mins = [p for p in players if p["min"]]
    if mins:
        parts = ", ".join(f'{p["name"]} (${p["base"]:,} salary)' if p.get("base") else p["name"] for p in mins)
        notes.append(f'* One-year veteran-minimum deals: {parts}. Each counts against the cap at the two-year minimum shown in the table; the league covers the rest of the salary.')
    for p in players:
        if p["cnote"] and p["cap_hit"]:
            notes.append(f'* {p["name"]}: {p["cnote"]}')
    if fn_rows:
        notes.append("† nba.com’s roster page lists a different number: " + "; ".join(fn_rows) + ". ESPN’s number is shown; confirm once the team publishes its opening-night roster.")
    if issues:
        notes.append("Source mismatch: " + "; ".join(issues) + ".")
    notes_html = "".join(f'<p class="ros-foot">{E(n)}</p>' for n in notes)

    total = len(players)
    deck = (f'{total} players under contract for training camp: {counts["standard"]} on standard deals, '
            f'{counts["two-way"]} on two-way deals and {counts["camp-e10"] + counts["camp"]} on non-guaranteed camp deals. '
            f'Sorted by position, then jersey number.')
    asof = mt(now)
    tpl = open(os.path.join(HERE, "roster_template.html")).read()
    # Rocky (mascot) is a permanent static card in the template, outside {{ROWS}}:
    # never counted as a player and never part of the ESPN/nba.com check above.
    if 'id="mascot"' not in tpl:
        print("TEMPLATE ERROR: the permanent Rocky mascot card (id=\"mascot\") is missing from roster_template.html", file=sys.stderr)
        sys.exit(3)
    out = (tpl.replace("{{DECK}}", E(deck)).replace("{{ASOF}}", E(asof))
              .replace("{{ROWS}}", "\n".join(body)).replace("{{NOTES}}", notes_html)
              .replace("{{STAFF}}", "".join(staff_html)).replace("{{INJURIES}}", inj_html)
              .replace("{{TOTAL}}", str(total)).replace("{{CHECKED}}", E(contracts.get("checked", ""))))
    open(a.out, "w").write(out)
    os.makedirs("/workspace/nuggets-data", exist_ok=True)
    json.dump({"generated": now.isoformat(), "asof_mt": asof, "players": players, "counts": counts,
               "coaches": coaches, "issues": issues},
              open(f"/workspace/nuggets-data/roster-{now.astimezone(MT):%Y-%m-%d}.json", "w"), indent=1, ensure_ascii=False)
    print(f"wrote {a.out}: {total} players {counts}; issues={issues}; jersey diffs={fn_rows}")


if __name__ == "__main__":
    main()
