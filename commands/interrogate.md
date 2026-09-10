---
description: Use for \"interrogate\", \"adversarial review\", \"multi-model review\", \"challenge this\", \"stress test this code\", \"find blind spots\"
agent: build
---
Load the `interrogate` skill with the skill tool and follow it end to end.
Run adversarial multi-model review of the diff under discussion. At fan-out and each drain, show the fleet board in your reply: run `python3 ~/.config/opencode/scripts/pstack-fleet.py --once --plain` via bash (fallback: this repo's `script/pstack-fleet.py`) and paste the board.
User request: $ARGUMENTS
