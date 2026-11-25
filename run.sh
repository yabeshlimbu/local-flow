#!/bin/zsh
# Start LocalFlow. First run creates the venv and installs dependencies.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
fi
pgrep -x ollama >/dev/null || (open -ga Ollama 2>/dev/null || (ollama serve >/dev/null 2>&1 &))
exec .venv/bin/python -m localflow "$@"
