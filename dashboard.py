#!/usr/bin/env python3
"""Compatibilidade: redireciona para o painel único servido pelo harness."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--sem-abrir", action="store_true")
    args = parser.parse_args()
    comando = [sys.executable, str(ROOT / "harness.py"), "painel", "--porta", str(args.porta)]
    if args.sem_abrir:
        comando.append("--sem-abrir")
    return subprocess.call(comando, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
