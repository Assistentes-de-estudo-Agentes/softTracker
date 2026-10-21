"""Servidor local do painel: serve painel/index.html e /api/status (sempre reflete o código de agora)."""
import json
import os
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import engine, estado as est, indexer, spec as spec_mod

PASTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "painel")


def _mtime(cfg, nome):
    try:
        return os.path.getmtime(os.path.join(cfg["estado"], nome))
    except OSError:
        return 0


def servir(cfg, porta=8765, abrir=True):
    trava, cache = threading.Lock(), {"chave": None, "estado": None, "checado": 0.0}

    def obter(forcar=False):
        with trava:
            if not forcar and cache["estado"] and time.time() - cache["checado"] < 2:
                return cache["estado"]  # no máximo uma indexação a cada 2 s
            try:
                spec = spec_mod.carregar(cfg["specs"])
                fp = indexer.indexar(cfg["projeto"], spec["ignorar"])["fp"]
                chave = (fp, spec["hash"], _mtime(cfg, est.MANUAIS), _mtime(cfg, est.NEGATIVOS))
                cache["checado"] = time.time()
                if forcar or chave != cache["chave"] or cache["estado"] is None:
                    with est.trava(cfg):
                        novo = engine.sincronizar(cfg, usar_ia=False, max_ia=0)
                    cache.update(chave=chave, estado=novo)
                return cache["estado"]
            except engine.ErroSpec as e:
                return {"erro_spec": list(e.args[0])}
            except SystemExit:  # outra execução do harness segura a trava: devolve o último estado
                return cache["estado"] or est.carregar(cfg) or {"erro": "Harness ocupado, tente de novo."}
            except Exception as e:
                return {"erro": f"{e.__class__.__name__}: {e}"}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=PASTA, **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("localhost", "127.0.0.1"):  # evita DNS rebinding
                self.send_error(403)
                return
            u = urlparse(self.path)
            if u.path == "/api/status":
                corpo = json.dumps(obter("forcar" in parse_qs(u.query)), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            else:
                super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)  # só aceita conexões desta máquina
    url = f"http://localhost:{porta}"
    print(f"Painel em {url}  (Ctrl+C para encerrar)")
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nPainel encerrado.")
    finally:
        srv.server_close()
