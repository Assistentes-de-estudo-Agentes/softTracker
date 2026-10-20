"""Estado em disco: status.json (fonte do painel), codigo.json (grafo) e vinculos_manuais.json."""
import contextlib
import json
import os
import shutil
import time

STATUS, CODIGO, MANUAIS, NEGATIVOS = "status.json", "codigo.json", "vinculos_manuais.json", "julgamentos_negativos.json"


def _p(cfg, nome):
    os.makedirs(cfg["estado"], exist_ok=True)
    return os.path.join(cfg["estado"], nome)


def _ler(cfg, nome, padrao):
    try:
        with open(_p(cfg, nome), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return padrao


def _gravar(cfg, nome, dados):
    destino = _p(cfg, nome)
    if os.path.exists(destino):
        shutil.copy2(destino, destino + ".bak")
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, destino)  # atômico


def carregar(cfg):
    return _ler(cfg, STATUS, {})


def carregar_manuais(cfg):
    return _ler(cfg, MANUAIS, {})


def salvar_manuais(cfg, manuais):
    _gravar(cfg, MANUAIS, manuais)


def carregar_negativos(cfg):
    return _ler(cfg, NEGATIVOS, {})


def salvar_negativos(cfg, negativos):
    _gravar(cfg, NEGATIVOS, negativos)


def salvar(cfg, estado, grafo):
    _gravar(cfg, CODIGO, grafo)
    _gravar(cfg, STATUS, estado)


@contextlib.contextmanager
def trava(cfg):
    caminho = _p(cfg, ".lock")
    if os.path.exists(caminho) and time.time() - os.path.getmtime(caminho) > 300:
        os.remove(caminho)  # trava velha de uma execução que caiu
    try:
        fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("Outra execução do harness está em andamento (estado/.lock).")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(caminho)
