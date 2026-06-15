# Competitive Analysis — June 2026

Research conducted 2026-06-15 via web search + direct page fetch.

## Competitors

### Chessigma — Chess Wrapped (free, annual)
**URL:** chessigma.com/wrapped  
**Closest to:** the "Wrapped" framing, not the coach framing

What it generates:
- Elo progression throughout the year + peak rating
- Opening repertoire with win rate per opening
- Win method breakdown (checkmate vs resignation)
- Best win of the year (with game link)
- Longest win streak
- Favorite time to play, longest chess binge, day-of-week trends
- "The Rival" — most faced opponent
- Chess personality match (Magnus, Tal, GothamChess, etc.)
- Cinematic experience with music and animations — built for social sharing

Platforms: Chess.com + Lichess  
Price: Free  
Cadence: Annual only (year-end)  
Gap vs Chess Lens: no monthly cadence, no actionable study plan, no game replay, no coach narrative

---

### AimChess ($58/year)
**Closest to:** the improvement/coach framing

What it does:
- Analyzes your games and generates personalized puzzles based on your specific weaknesses
- Data-driven improvement analytics
- Best fit: 1400-1800 ELO (statistically meaningful, subtle enough for pattern analysis)
- Below 1400: less effective — player hasn't generated enough consistent data

Gap vs Chess Lens: no narrative reports, no game replay / time travel, no study roadmap — just puzzles

---

### ChessMonitor (freemium)
**URL:** chessmonitor.com  
**Closest to:** opponent preparation and deep analytics

What it does:
- Opponent scouting with detailed statistics
- 30B+ online games database + 10M OTB/tournament games (Ultra Database)
- Opening explorer, custom PGN import
- FIDE Elo estimation
- Mobile apps (iOS + Android)
- Received startup grant 2024; Anish Giri (Top 10 world) joined team Oct 2025

Tiers:
- Free: basic analytics, 1 account per platform
- Plus: 5 accounts, Ultra Database, advanced filters, ad-free
- Pro: coaches/clubs, 10 accounts, tournament prep

Gap vs Chess Lens: no narrative coach, no replay/time travel, no personalized study plan — oriented toward pre-game preparation, not post-game learning

---

### chesswrap.me (free, annual)
Simple Wrapped clone. Chess.com only. Basic stats: games, W/L/D, openings. Open source on GitHub. No narrative, no analysis depth.

---

### Chess Insights ($18/year)
Dashboard + AI narrative report. No replay feature, no personalized roadmap.

---

### chess.com Diamond ($99/year)
Full game analysis with engine. Most complete but expensive. No replay/time-travel UX, no AI coach narrative.

---

## Gap matrix

| Feature | Chessigma | AimChess | ChessMonitor | Chess Lens |
|---|---|---|---|---|
| Monthly reports | ❌ annual | ❌ | ❌ | ✅ |
| Narrative coach | ✅ storytelling only | ❌ | ❌ | ✅ actionable |
| Personalized study plan | ❌ | ⚠️ puzzles only | ❌ | ✅ |
| Game replay / time travel | ❌ | ❌ | ❌ | ✅ |
| Free tier with AI | ✅ | ❌ | ⚠️ basic | ✅ (Ollama) |
| Stockfish analysis | ❌ | ✅ | ✅ | ✅ |
| Maia integration | ❌ | ❌ | ❌ | 🔜 Phase 3 |

## Key insight

The "Chess Wrapped" framing is a hook, not the product. Every competitor either does Wrapped (Chessigma, cinematic and free) or does analytics (AimChess, ChessMonitor). Nobody combines:
1. Post-game narrative with specific study recommendations
2. Interactive replay from the exact losing move

The time-travel replay feature is the real differentiator. It's what a human chess coach does in a lesson — "go back to move 23, what would you play here?" — automated.

## Failure cases to study

- **Chess24** — shut down Jan 2024. Not a failure: Chess.com acquired Play Magnus (Chess24's parent) and consolidated. Not product failure.
- No documented startup failures found in the coach/analytics niche specifically.

## Risk: the discipline gap

AimChess learned that their product works best at 1400+ ELO. Below that, players don't have the discipline to use systematic improvement tools consistently. Chess Lens targets 1000-1600 — the lower half of that range is a risk. Validate retention with real users at the local chess workshop before building Phase 2.
