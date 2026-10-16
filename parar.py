#!/usr/bin/env python3
"""Request graceful shutdown of this copy only; never kill games or Ollama."""
import os
from pathlib import Path
import signal
from settings import CODE_DIR, STATE_DIR


def main():
    try:
        pid = int((STATE_DIR / '.tradutor.pid').read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if str(CODE_DIR / 'main.py').encode() not in args:
            raise SystemExit('PID não corresponde a esta cópia; nada foi parado.')
        os.kill(pid, signal.SIGTERM)
        print('Encerramento solicitado. Aguarde a liberação do modelo próprio.')
    except (OSError, ValueError):
        print('Esta cópia não está aberta.')


if __name__ == '__main__':
    main()
