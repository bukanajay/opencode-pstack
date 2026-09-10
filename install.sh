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

case "$MODE" in
  --global)
    install_dir "$SRC/skills" "$HOME/.config/opencode/skills"
    install_dir "$SRC/agents" "$HOME/.config/opencode/agents"
    install_dir "$SRC/commands" "$HOME/.config/opencode/commands"
    ;;
  --project)
    install_dir "$SRC/skills" "$TARGET_DIR/.opencode/skills"
    install_dir "$SRC/agents" "$TARGET_DIR/.opencode/agents"
    install_dir "$SRC/commands" "$TARGET_DIR/.opencode/commands"
    ;;
  *)
    echo "usage: ./install.sh [--global | --project [DIR]]" >&2
    exit 1
    ;;
esac

echo "done. In opencode, run /setup-pstack once to map roles to your models."
