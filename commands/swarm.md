---
description: Fan out N parallel workers, drain them, and return one report.
agent: build
---
Load the `swarm` skill with the skill tool and follow it end to end.
Fan out parallel workers via the task tool, drain them, return one report. At fan-out and each drain, show the fleet board in your reply: run `python3 ~/.config/opencode/scripts/pstack-fleet.py --once --plain` via bash (fallback: this repo's `script/pstack-fleet.py`) and paste the board.
User request: $ARGUMENTS
