#!/usr/bin/env python3
"""Build docs/jokic-triple-doubles.html from tools/td_data.json (hand-maintained; never fetches or invents).
Add every Jokić regular-season game to games_checked after it ends (ESPN box score); the
script counts triple-doubles itself (10+ in 3 of pts/reb/ast/stl/blk).
Usage: python3 tools/build_td.py [--out docs/jokic-triple-doubles.html]"""
import argparse, html, json, os
from datetime import date
H=os.path.dirname(os.path.abspath(__file__)); E=lambda s: html.escape(str(s))
EXT='target="_blank" rel="noopener noreferrer"'
ap=argparse.ArgumentParser(); ap.add_argument('--asof', default=None); ap.add_argument('--out', default=os.path.join(H,'..','docs','jokic-triple-doubles.html')); a=ap.parse_args()
d=json.load(open(os.path.join(H,'td_data.json'))); t=open(os.path.join(H,'td_template.html')).read()
is_td=lambda g: sum(1 for k in ('pts','reb','ast','stl','blk') if (g.get(k) or 0)>=10)>=3
games=sorted(d['games_checked'], key=lambda g:g['date']); tds=[g for g in games if is_td(g)]
base=d['career_before_season']; career=base+len(tds); rec=d['record']['count']; holder=d['record']['holder']
fmt=lambda s: date.fromisoformat(s).strftime('%a %b %-d, %Y')
rows=''.join(f'<tr><td data-label="#">{i}</td><td data-label="Career #">{base+i}</td><td data-label="Date">{fmt(g["date"])}</td><td data-label="Opponent"><a href="https://www.espn.com/nba/boxscore/_/gameId/{g["espn_id"]}" {EXT}>{E(g["opp"])}</a></td><td data-label="PTS">{g["pts"]}</td><td data-label="REB">{g["reb"]}</td><td data-label="AST">{g["ast"]}</td><td data-label="Result">{E(g["result"])}</td></tr>' for i,g in enumerate(tds,1)) or '<tr><td colspan="8">None yet this season.</td></tr>'
if career<rec: status=f'{rec-career} to tie · {rec-career+1} to break'; gl,gap,gs='To tie the record',rec-career,f'{rec-career+1} to set a new record'
elif career==rec: status='Tied for the record'; gl,gap,gs='Behind the record',0,'tied; 1 more sets the record'
else: status='NBA record holder'; gl,gap,gs='Ahead of Westbrook',f'+{career-rec}',f'Jokić holds the record ({career})'
if career>rec: holder_txt=f'Jokić {career} (was {holder}, {rec})'; recshow=career
else: holder_txt=f'{holder} ({d["record"]["note"]})'; recshow=rec
last=games[-1] if games else None
lasttxt=f'{fmt(last["date"])} {E(last["opp"])}: {last["pts"]} pts, {last["reb"]} reb, {last["ast"]} ast, {last["stl"]} stl, {last["blk"]} blk ({"triple-double" if is_td(last) else "not a triple-double"}).' if last else 'no games yet.'
board=''.join(f'<tr{" class=\"td-den\"" if "Joki" in n else ""}><td data-label="Rank">{i}</td><td data-label="Player">{E(n)}</td><td data-label="Triple-doubles">{career if "Joki" in n else c}</td><td data-label="Status">{E(s)}</td></tr>' for i,(n,c,s) in enumerate(sorted(d['leaders'],key=lambda x:-(career if "Joki" in x[0] else x[1])),1))
rep=dict(DECK=f'Nikola Jokić has {len(tds)} triple-double{"s" if len(tds)!=1 else ""} in 2026–27 and {career} in his regular-season career. {holder} holds the NBA record with {rec}.' if career<=rec else f'Jokić holds the NBA record with {career} career triple-doubles.',
 ASOF=d['checked'],STATUS=status,SEASON=len(tds),GP=f'{len(games)} game'+('s' if len(games)!=1 else ''),CAREER=career,REC=recshow,HOLDER=E(holder_txt),GAPLABEL=gl,GAP=gap,GAPSUB=gs,
 PCT=f'{min(career/rec,1)*100:.1f}',NOTE=f'Jokić started the season with {base} (Basketball-Reference; NBA.com agrees). Bar shows his career total as a share of the {rec} record.',
 ROWS=rows,LAST=lasttxt,BOARD=board,CHECKED=d['checked'],SRCS=' '.join(f'<a href="{u}" {EXT}>{E(n)}</a>' for n,u in d['sources']))
for k,v in rep.items(): t=t.replace('{'+k+'}',str(v))
t=t.replace('{{','{').replace('}}','}')
open(a.out,'w').write(t); print(f'season {len(tds)} / {len(games)} GP · career {career} · record {rec} ({holder}) · {status}')
