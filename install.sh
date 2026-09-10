#!/bin/sh
# Install opencode-pstack skills/agents/commands.
#   ./install.sh --global            -> ~/.config/opencode/{skills,agents,commands}
#   ./install.sh --project [DIR]     -> DIR/.opencode/{skills,agents,commands} (default DIR=.)
set -eu

SRC="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:- --global}"
TARGET_DIR="${2:-.}"

install_dir() {
  # $1 = source dir, $2 = dest dir
  mkdir -p "$2"
  cp -R "$1/." "$2/"
  echo "installed $1 -> $2"
}

install_script() {
  # $1 = dest base dir (.opencode or ~/.config/opencode)
  mkdir -p "$1/scripts"
  cp "$SRC/script/pstack-fleet.py" "$1/scripts/pstack-fleet.py"
  cp "$SRC/script/pstack-fleet-serve.py" "$1/scripts/pstack-fleet-serve.py"
  echo "installed $SRC/script/pstack-fleet*.py -> $1/scripts/"
}

case "$MODE" in
  --global)
    install_dir "$SRC/skills" "$HOME/.config/opencode/skills"
    install_dir "$SRC/agents" "$HOME/.config/opencode/agents"
    install_dir "$SRC/commands" "$HOME/.config/opencode/commands"
    if [ -d "$SRC/plugins" ]; then
      install_dir "$SRC/plugins" "$HOME/.config/opencode/plugins"
    fi
    if [ -d "$SRC/fleet" ]; then
      install_dir "$SRC/fleet" "$HOME/.config/opencode/fleet"
    fi
    install_script "$HOME/.config/opencode"
    ;;
  --project)
    install_dir "$SRC/skills" "$TARGET_DIR/.opencode/skills"
    install_dir "$SRC/agents" "$TARGET_DIR/.opencode/agents"
    install_dir "$SRC/commands" "$TARGET_DIR/.opencode/commands"
    if [ -d "$SRC/plugins" ]; then
      install_dir "$SRC/plugins" "$TARGET_DIR/.opencode/plugins"
    fi
    if [ -d "$SRC/fleet" ]; then
      install_dir "$SRC/fleet" "$TARGET_DIR/.opencode/fleet"
    fi
    install_script "$TARGET_DIR/.opencode"
    ;;
  *)
    echo "usage: ./install.sh [--global | --project [DIR]]" >&2
    exit 1
    ;;
esac

echo "done. In opencode, run /setup-pstack once to map roles to your models."
