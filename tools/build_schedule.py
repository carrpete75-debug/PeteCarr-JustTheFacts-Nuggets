#!/usr/bin/env python3
"""Build docs/schedule.html (full Nuggets season schedule) from live data.

Data: ESPN site API (team 7 schedule, seasontype=1 preseason, 2 regular) is the
primary list/results source; nba.com/nuggets/schedule (__NEXT_DATA__) supplies
local TV (Altitude) + national TV and the Nuggets' official ticket links; each
host team's official nba.com/<slug>/schedule supplies road-game ticket links
(static __NEXT_DATA__, or a headless-Chrome DOM render for custom team pages).
No resale links (ESPN's Vivid Seats links are ignored).

Usage: python3 tools/build_schedule.py [--season 2027] [--out docs/schedule.html]
Writes a fact pack to /workspace/nuggets-data/schedule-YYYY-MM-DD.json.
"""
import argparse, html, json, os, re, subprocess, sys, urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DATA_DIR = "/workspace/nuggets-data/sched"
TRACK_KEYS = ("wt.mc_id", "aid", "pid", "camefrom", "promo_id", "promo_name", "promo_position")


def get(url, timeout=40, ua=True):
    cmd = ["curl", "-sSL", "--fail", "--max-time", str(timeout)] + (["-A", UA] if ua else []) + [url]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def redirect_target(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return e.headers.get("Location")
    except Exception:
        return None
    return None


def clean(u):
    if not u:
        return u
    u = html.unescape(u)
    p = urlsplit(u)
    q = [(k, v) for k, v in parse_qsl(p.query) if not (k.lower().startswith("utm_") or k.lower() in TRACK_KEYS)]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def next_data(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    d = json.loads(m.group(1))
    return ((d.get("props", {}).get("pageProps", {}).get("scheduleData") or {}).get("schedule")) or []


def chrome_dom(url):
    try:
        out = subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
                              "--virtual-time-budget=25000", f"--user-agent={UA}", "--dump-dom", url],
                             capture_output=True, text=True, timeout=120)
        return out.stdout
    except Exception:
        return ""


TICKET_RE = re.compile(r"ticketmaster\.|seatgeek\.com|evenue\.net|axs\.com|tickets\.[a-z]+\.com", re.I)


def ticket_from_dom(dom, g):
    """Find the host team's published ticket link for game g in a rendered team schedule page."""
    gid = g["gameId"]
    local = g["gameDateEst"][:10].replace("-", "")
    gcode = f"{local}/DEN{g['homeTeam']['teamTricode']}"
    # JSON-LD SportsEvent offers (e.g. Heat)
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', dom, re.S):
        if gid not in m.group(1):
            continue
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        items = j.get("itemListElement", [j]) if isinstance(j, dict) else j
        for it in items:
            it = it.get("item", it) if isinstance(it, dict) else it
            if isinstance(it, dict) and gid in json.dumps(it):
                offers = it.get("offers") or []
                offers = offers if isinstance(offers, list) else [offers]
                for o in offers:
                    if TICKET_RE.search(o.get("url", "")):
                        return o["url"]
    # Kings-style: camefrom code carries the local game date as EK<2-digit season code><MMDD>
    mmdd = local[4:]
    for u in re.findall(r'href="([^"]+)"', dom):
        if re.search(rf"_EK\d\d{mmdd}_", u) and "brand=kings" in u.lower() and TICKET_RE.search(u):
            return u
    # data-gameid="YYYYMMDD/DENXXX" on the ticket anchor itself (Nets)
    m = re.search(r'<a[^>]*data-gameid="%s"[^>]*>' % re.escape(gcode), dom)
    if m:
        h = re.search(r'href="([^"]+)"', m.group(0))
        if h and TICKET_RE.search(h.group(1)):
            return h.group(1)
    # game block that starts at the gameId / gcode marker, ends at the next game marker
    for m in re.finditer(re.escape(gid), dom):
        seg = dom[m.end(): m.end() + 8000]
        nxt = None
        for mm in re.finditer(r'00[1-4]2\d{6}|data-gameid="\d{8}/[A-Z]{6}"', seg):
            if gid not in mm.group(0) and gcode not in mm.group(0):
                nxt = mm
                break
        seg = seg[: nxt.start()] if nxt else seg
        for u in re.findall(r'href="([^"]+)"', seg):
            if TICKET_RE.search(u):
                return u
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2027")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "docs", "schedule.html"))
    ap.add_argument("--no-chrome", action="store_true")
    a = ap.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(MT)
    gaps = []

    espn = {}
    for st in (1, 2):
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/7/schedule?seasontype={st}&season={a.season}"
        espn[st] = json.loads(get(url, ua=False)).get("events", [])
        json.dump(espn[st], open(f"{DATA_DIR}/espn_st{st}.json", "w"))

    den_page = get("https://www.nba.com/nuggets/schedule")
    nba = [g for g in next_data(den_page) if g.get("gameId", "")[:3] in ("001", "002")]
    json.dump(nba, open(f"{DATA_DIR}/nba_den_games.json", "w"))
    nba_by_time = {g["gameTimeUTC"][:16]: g for g in nba}
    nba_by_date = {}
    for g in nba:
        nba_by_date.setdefault(datetime.fromisoformat(g["gameTimeUTC"].replace("Z", "+00:00")).astimezone(MT).date(), g)

    host_cache, dom_cache = {}, {}

    def road_ticket(g):
        slug = g["homeTeam"]["teamSlug"]
        fallback = (f"https://www.nba.com/{slug}/tickets", "general", f"{g['homeTeam']['teamName']} official tickets page")
        if slug not in host_cache:
            try:
                host_cache[slug] = next_data(get(f"https://www.nba.com/{slug}/schedule"))
            except Exception:
                host_cache[slug] = []
        hit = [x for x in host_cache[slug] if isinstance(x, dict) and x.get("gameId") == g["gameId"]]
        if hit:
            t = hit[0].get("tickets") or {}
            u = t.get("singleTickets") or t.get("schedule")
            if u and TICKET_RE.search(u):
                return clean(u), "event", f"{g['homeTeam']['teamName']} official schedule"
            return fallback
        if a.no_chrome:
            return fallback
        if slug not in dom_cache:
            dom_cache[slug] = chrome_dom(f"https://www.nba.com/{slug}/schedule")
        u = ticket_from_dom(dom_cache[slug], g)
        if u:
            return clean(u), "event", f"{g['homeTeam']['teamName']} official schedule"
        return fallback

    def home_ticket(g):
        t = g.get("tickets") or {}
        u = t.get("singleTickets") or t.get("schedule")
        if not u:
            return "https://www.nba.com/nuggets/tickets", "general", "Nuggets official tickets page"
        if "nuggets.media" in u:
            tgt = redirect_target(u)
            if tgt and "ticketmaster" in tgt:
                return clean(tgt), "event", "Nuggets official schedule"
            return u, "event", "Nuggets official schedule (short link)"
        src = "CU Athletics via Nuggets schedule" if "cubuffs" in u else "Nuggets official schedule"
        return clean(u), "event", src

    rows = []
    for st in (1, 2):
        rec = [0, 0]
        for e in sorted(espn[st], key=lambda x: x["date"]):
            c = e["competitions"][0]
            dt_utc = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            dt = dt_utc.astimezone(MT)
            den = next(x for x in c["competitors"] if x["id"] == "7")
            opp = next(x for x in c["competitors"] if x["id"] != "7")
            home = den["homeAway"] == "home"
            status = c["status"]["type"]
            g = nba_by_time.get(dt_utc.strftime("%Y-%m-%dT%H:%M")) or nba_by_date.get(dt.date())
            venue = c.get("venue", {})
            addr = venue.get("address", {})
            city = ", ".join(x for x in (addr.get("city"), addr.get("state")) if x)
            if g and g.get("arenaName"):
                vname = g["arenaName"]
                city = ", ".join(x for x in (g.get("arenaCity"), g.get("arenaState")) if x) or city
            else:
                vname = venue.get("fullName", "")
            # TV
            nat, loc = [], []
            if g:
                b = g.get("broadcasters") or {}
                nat = [x["broadcasterDisplay"] for x in b.get("nationalBroadcasters", []) if x.get("broadcasterDisplay") and x["broadcasterDisplay"] != "TBD"]
                side = "homeTvBroadcasters" if home else "awayTvBroadcasters"
                loc = [x["broadcasterDisplay"] for x in b.get(side, []) if x.get("broadcasterDisplay")]
            if not nat:
                nat = [x.get("media", {}).get("shortName") for x in c.get("broadcasts", []) if x.get("media", {}).get("shortName")]
            tv = " · ".join(dict.fromkeys(nat + loc))
            label = (g or {}).get("gameLabel") or ""
            sub = (g or {}).get("gameSubLabel") or ""
            label = "" if label == "Preseason" else label
            row = dict(espn_id=e["id"], nba_game_id=(g or {}).get("gameId"), season_type="preseason" if st == 1 else "regular",
                       utc=e["date"], date_mt=dt.strftime("%a, %b %-d"), month=dt.strftime("%B %Y"),
                       time_mt=dt.strftime("%-I:%M %p ") + dt.tzname() if c.get("timeValid", True) else "TBD",
                       home=home, opp=opp["team"].get("shortDisplayName") or opp["team"]["displayName"],
                       opp_full=opp["team"]["displayName"], venue=vname, city=city, tv=tv,
                       label=(label + (f" · {sub}" if sub else "")).strip(), state=status.get("state"),
                       detail=status.get("detail") or status.get("description"))
            if status.get("completed"):
                ds = float((den.get("score") or {}).get("value", 0))
                os_ = float((opp.get("score") or {}).get("value", 0))
                win = den.get("winner", ds > os_)
                rec[0 if win else 1] += 1
                ot = ""
                m = re.search(r"(\d?OT)", status.get("detail", ""))
                if m:
                    ot = f" ({m.group(1)})"
                row.update(result="W" if win else "L", score=f"{int(ds)}–{int(os_)}{ot}", record=f"{rec[0]}–{rec[1]}")
            elif status.get("state") == "post" or status.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"):
                row.update(result=None, note=status.get("description"))
            else:
                if g:
                    u, kind, src = home_ticket(g) if home else road_ticket(g)
                else:
                    u, kind, src = ("https://www.nba.com/nuggets/tickets", "general", "Nuggets official tickets page") if home else (None, None, None)
                    gaps.append(f"No nba.com match for ESPN event {e['id']} ({row['date_mt']}); ticket link fallback")
                row.update(ticket_url=u, ticket_type=kind, ticket_source=src)
            rows.append(row)

    pre = [r for r in rows if r["season_type"] == "preseason"]
    reg = [r for r in rows if r["season_type"] == "regular"]
    if len(reg) < 82:
        gaps.append(f"{82 - len(reg)} regular-season game(s) not yet scheduled (set by Emirates NBA Cup results); ESPN and nba.com both list {len(reg)}")
    for r in rows:
        if not r["tv"]:
            gaps.append(f"TV not listed: {r['date_mt']} {'vs' if r['home'] else '@'} {r['opp']}")

    def rec_of(rs):
        done = [r for r in rs if r.get("result")]
        return f"{sum(r['result']=='W' for r in done)}–{sum(r['result']=='L' for r in done)}", len(done)

    pre_rec, pre_done = rec_of(pre)
    reg_rec, reg_done = rec_of(reg)
    asof = now.strftime("%a %b %-d, %Y · %-I:%M %p ") + now.tzname()
    json.dump(dict(generated_mt=now.isoformat(), counts=dict(preseason=len(pre), regular=len(reg)), records=dict(preseason=pre_rec, regular=reg_rec),
                   games=rows, data_gaps=gaps), open(f"/workspace/nuggets-data/schedule-{now:%Y-%m-%d}.json", "w"), indent=1)

    E = html.escape

    def tr(r):
        cls = ' class="is-home"' if r["home"] else ""
        vs = "vs" if r["home"] else "@"
        tag = f'<span class="sched-tag">{E(r["label"])}</span>' if r["label"] else ""
        if r.get("result"):
            res_cls = "sched-w" if r["result"] == "W" else "sched-l"
            res = f'<span class="{res_cls}">{r["result"]}</span> {E(r["score"])} <span class="sched-rec">({r["record"]})</span>'
        elif r.get("note"):
            res = f'<span class="unavail">{E(r["note"])}</span>'
        else:
            res = E(r["time_mt"])
        tv = E(r["tv"]) if r["tv"] else '<span class="unavail">TBD</span>'
        if r.get("ticket_url"):
            where = "Ball Arena" if r["home"] and r["venue"] == "Ball Arena" else r["venue"]
            aria = f'Tickets: {r["opp"]} at Nuggets' if r["home"] else f'Tickets: Nuggets at {r["opp"]}'
            aria += f', {r["date_mt"].split(", ")[1]}, {where} ({r["ticket_source"]})'
            tix = f'<a class="ticket-link" href="{E(r["ticket_url"])}" target="_blank" rel="noopener noreferrer" aria-label="{E(aria)}">Tickets</a>'
        else:
            tix = ""
        return (f'<tr{cls}><td data-label="Date">{E(r["date_mt"])}</td>'
                f'<td data-label="Opponent"><span class="sched-ha">{vs}</span> {E(r["opp"])}{tag}</td>'
                f'<td data-label="Venue">{E(r["venue"])}<span class="sched-city">{E(r["city"])}</span></td>'
                f'<td data-label="Time / result">{res}</td><td data-label="TV">{tv}</td>'
                f'<td data-label="Tickets" class="sched-tix">{tix}</td></tr>')

    head = ('<thead><tr><th scope="col">Date (MT)</th><th scope="col">Opponent</th><th scope="col">Venue</th>'
            '<th scope="col">Time (MT) / result</th><th scope="col">TV</th><th scope="col"><span class="sr-only">Tickets</span></th></tr></thead>')

    def section(sid, title, rs, extra=""):
        n_home = sum(r["home"] for r in rs)
        return (f'    <section class="card sched-month" aria-labelledby="{sid}">\n'
                f'      <div class="card-head"><h2 id="{sid}">{E(title)}</h2><span class="sched-count">{len(rs)} games · {n_home} home</span></div>\n'
                f'      {extra}<div class="table-wrap"><table class="facts sched-table">{head}<tbody>\n        '
                + "\n        ".join(tr(r) for r in rs) + "\n      </tbody></table></div>\n    </section>\n")

    sections = [section("pre-heading", "Preseason · October 2026", pre)]
    months = []
    for r in reg:
        if r["month"] not in months:
            months.append(r["month"])
    tbd_n = 82 - len(reg)
    for m in months:
        rs = [r for r in reg if r["month"] == m]
        extra = ""
        if m.startswith("December") and tbd_n > 0:
            extra = (f'<p class="note"><span class="unavail">{tbd_n} more regular-season games are not scheduled yet. '
                     'The NBA sets them after the Emirates NBA Cup group stage, so dates depend on Cup results.</span></p>\n      ')
        sections.append(section("m-" + m.split()[0].lower(), m + " · regular season", rs, extra))

    tpl = open(os.path.join(os.path.dirname(__file__), "schedule_template.html")).read()
    n_event = sum(1 for r in rows if r.get("ticket_type") == "event")
    n_general = sum(1 for r in rows if r.get("ticket_type") == "general")
    out = (tpl.replace("{{ASOF}}", E(asof))
              .replace("{{PRE_N}}", str(len(pre))).replace("{{REG_N}}", str(len(reg)))
              .replace("{{PRE_REC}}", pre_rec).replace("{{REG_REC}}", reg_rec)
              .replace("{{HOME_N}}", str(sum(r["home"] for r in reg))).replace("{{AWAY_N}}", str(sum(not r["home"] for r in reg)))
              .replace("{{TBD_N}}", str(tbd_n))
              .replace("{{TIX_EVENT}}", str(n_event)).replace("{{TIX_GENERAL}}", str(n_general))
              .replace("{{SECTIONS}}", "".join(sections)))
    open(a.out, "w").write(out)
    print(json.dumps(dict(preseason=len(pre), regular=len(reg), pre_rec=pre_rec, reg_rec=reg_rec,
                          tickets_event=n_event, tickets_general=n_general, gaps=gaps), indent=1))


if __name__ == "__main__":
    main()
