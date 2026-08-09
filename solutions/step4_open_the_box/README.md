# Module 3 — Open the box

Same agent, now leaving a trail in four different places.

**New here**
| File | What it adds |
|---|---|
| `memory.py` | `recall()` / `remember()` over `memory/*.md` |
| `tools.py` | seat map → **artifact**; summary → `temp:`; companions → `user:` |

**Go find, in the dev UI**
1. `user:prefs` — State tab
2. `temp:seatmap` and its age — State tab
3. compaction summaries — Events tab
4. `seatmap_*.json` — Artifacts tab
5. past bookings — `memory/userx.md`, in no session at all

Then predict which survive a restart, and restart. Most people get `temp:` wrong.
