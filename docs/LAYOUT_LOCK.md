# Layout lock (Nuggets Desk, launched 2026-09-30)

Cloned from the approved Broncos Desk layout (locked 2026-09-23). Do not redesign without an explicit user request. Daily runs update content only unless fixing a real bug.

1. **Banner**: compact centered CSS `.nuggets-banner` (DENVER NUGGETS / gold rule / JUST THE FACTS + corner accents in gold with a thin sunshine-red stripe) above the brand/nav row. Not image-based; not 2× height.
2. **Rail + main**: full-width flush-left `.page-shell`; `.northwest-rail` beside `<main>` (`clamp(15rem, 20vw, 19.5rem)`, ~1.05rem type, ~0.4rem left pad). Keep it flush to the left edge of the gold page.
   - Tile 1 `aside.northwest-standings`: Northwest Division standings (Thunder, Nuggets, Timberwolves, Trail Blazers, Jazz) ordered by current division rank. Columns Team / W–L / third column (PCT during the season; last season's record while everyone is 0–0). Nuggets row `tr.is-den`. Title links to ESPN division standings (new tab).
   - Tile 2 `aside.northwest-standings.northwest-standings--odds`: Team / Div / Title American odds (Nuggets row `is-den`), muted source line with book + "as of" time in MT. 0.75rem gap under tile 1.
3. **Chrome / palette** (`:root` in styles.css): page `--gold #FEC524`, white tiles, header/footer `--navy #0E2240`, links `--navy-soft #1D428A`, highlight `--gold-soft #fff8e1`, badge text `--gold-deep #7a5a00`, hover/kicker accent `--red #8B2131` (sparingly). **Never use gold as text on white** (1.6:1 contrast); gold is for backgrounds, rules, borders and bars only.
4. **Card order in `.grid`**: Record (span-2, with last-game/last-season writeup) → Last game (span-2) → Next | Sportsbook odds (one column each) → Kalshi (span-2, separate from sportsbooks) → Injuries (span-2) → Upcoming (span-2, next ~5–6 games incl. preseason) → Ball Arena & team news (span-2) → Championship odds top 5 West/East (span-2). No weather card.
5. **Honesty rule**: never fabricate figures. When a number isn't available, say so on the card using `<span class="unavail">…</span>` (e.g. "Lines not posted yet"). Every card ends with a `.source-row`; odds and markets carry an "as of" time in MT.
6. External links use `target="_blank" rel="noopener noreferrer"`; same-site links stay relative.
7. Archive: prior home page is frozen to `docs/archive/YYYY-MM-DD.html` (fix relative paths to `../styles.css`, `../index.html`), newest first in `docs/archive/index.html`.
