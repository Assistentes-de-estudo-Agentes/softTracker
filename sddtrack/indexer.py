"""Indexa a pasta do projeto em um grafo de nós (arquivo, função, classe, rota) com hash.

Sem dependências externas e sem IA. Tolera código incompleto (projeto em construção):
se o arquivo Python não compila, usa expressões regulares no lugar do `ast`.
"""
import ast
import fnmatch
import hashlib
import os
import re

PASTAS_PADRAO = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                 ".idea", ".vscode", ".next", "target", ".pytest_cache"}
MAX_BYTES = 800_000
MAX_LINHAS_NO = 120

_JS = [("funcao", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"),
       ("classe", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"),
       ("funcao", r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>")]
_JAVA = [("classe", r"\b(?:class|interface|enum|record)\s+(\w+)"),
         ("funcao", r"^\s*(?:public|private|protected|internal|static|final|async|override|\s)+[\w<>\[\],.? ]+\s+(\w+)\s*\([^;{]*\)\s*(?:throws [\w, .]+)?\s*\{?\s*$"),
         ("funcao", r"\bfun\s+(\w+)")]
REGEX_POR_EXT = {
    ".py": [("funcao", r"^\s*(?:async\s+)?def\s+(\w+)"), ("classe", r"^\s*class\s+(\w+)")],
    ".js": _JS, ".jsx": _JS, ".ts": _JS, ".tsx": _JS, ".mjs": _JS, ".cjs": _JS, ".vue": _JS, ".svelte": _JS,
    ".java": _JAVA, ".kt": _JAVA, ".cs": _JAVA,
    ".go": [("funcao", r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("), ("classe", r"^type\s+(\w+)\s+(?:struct|interface)")],
    ".rb": [("funcao", r"^\s*def\s+(?:self\.)?(\w+[?!]?)"), ("classe", r"^\s*class\s+(\w+)")],
    ".php": [("funcao", r"\bfunction\s+(\w+)\s*\("), ("classe", r"\bclass\s+(\w+)")],
    ".rs": [("funcao", r"\bfn\s+(\w+)"), ("classe", r"\bstruct\s+(\w+)")],
}
REGEX_POR_EXT = {e: [(t, re.compile(r)) for t, r in lst] for e, lst in REGEX_POR_EXT.items()}

# Rotas: cada padrão devolve (método, caminho)
_M = r"(get|post|put|delete|patch)"
ROTAS = [
    (re.compile(r"""\b\w*(?:app|router|server|route|api|bp|blueprint)\w*\.""" + _M + r"""\(\s*['"`]([^'"`]+)['"`]""", re.I),
     lambda m: (m.group(1), m.group(2))),
    (re.compile(r"""@\w+\.""" + _M + r"""\(\s*['"]([^'"]+)['"]""", re.I), lambda m: (m.group(1), m.group(2))),
    (re.compile(r"""@\w*\.?route\(\s*['"]([^'"]+)['"](?:[^)]*methods\s*=\s*\[\s*['"](\w+)['"])?""", re.I),
     lambda m: (m.group(2) or "GET", m.group(1))),
    (re.compile(r"""@(Get|Post|Put|Delete|Patch)(?:Mapping)?\(\s*['"]?([^'")\s]*)"""),
     lambda m: (m.group(1), m.group(2))),
]


def _ignorado(rel, padroes):
    partes = rel.split("/")
    if any(p in PASTAS_PADRAO for p in partes[:-1]):
        return True
    for p in padroes:
        if p.endswith("/**"):
            base = p[:-3].rstrip("/")
            if rel == base or rel.startswith(base + "/") or base in partes[:-1]:
                return True
        elif fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(partes[-1], p):
            return True
    return False


def _hash(linhas):
    texto = "\n".join(l.rstrip() for l in linhas).strip()
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _normalizar_rota(metodo, caminho):
    caminho = re.sub(r"(:\w+|\{[^}]+\}|<[^>]+>)", "*", caminho.strip()) or "/"
    if not caminho.startswith("/"):
        caminho = "/" + caminho
    if len(caminho) > 1:
        caminho = caminho.rstrip("/")
    return f"{metodo.upper()} {caminho}"


def _entradas_python_ast(texto):
    """Funções e classes (com métodos como Classe.metodo) e faixa exata de linhas."""
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return None
    saida = []

    def visitar(no, prefixo=""):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nome = prefixo + filho.name
                ini = min([filho.lineno] + [d.lineno for d in filho.decorator_list])
                tipo = "classe" if isinstance(filho, ast.ClassDef) else "funcao"
                saida.append({"tipo": tipo, "nome": nome, "ini": ini, "fim": filho.end_lineno})
                if tipo == "classe":
                    visitar(filho, nome + ".")
            else:
                visitar(filho, prefixo)
    visitar(arvore)
    return saida


def _entradas_arquivo(ext, texto, linhas):
    entradas = []
    ast_ok = _entradas_python_ast(texto) if ext == ".py" else None
    if ast_ok is not None:
        entradas += ast_ok
    else:
        for i, linha in enumerate(linhas, 1):
            for tipo, rx in REGEX_POR_EXT.get(ext, []):
                m = rx.search(linha)
                if m:
                    entradas.append({"tipo": tipo, "nome": m.group(1), "ini": i})
                    break
    for i, linha in enumerate(linhas, 1):
        for rx, extrair in ROTAS:
            m = rx.search(linha)
            if m:
                metodo, caminho = extrair(m)
                entradas.append({"tipo": "rota", "nome": _normalizar_rota(metodo, caminho), "ini": i, "rota": True})
                break
    # faixas de linhas para entradas sem `fim` (regex): até o próximo símbolo
    inicios = sorted({e["ini"] for e in entradas})
    for e in entradas:
        if "fim" not in e:
            seguintes = [x for x in inicios if x > e["ini"]]
            limite = (seguintes[0] - 1) if seguintes else len(linhas)
            e["fim"] = max(e["ini"], min(limite, e["ini"] + MAX_LINHAS_NO - 1))
    # rota decorando/dentro de uma função na mesma linha ou logo abaixo: herda a faixa da função
    funcoes = [f for f in entradas if f["tipo"] == "funcao"]
    for e in entradas:
        if e.get("rota"):
            for f in funcoes:
                if 0 <= f["ini"] - e["ini"] <= 3:
                    e["fim"] = max(e["fim"], f["fim"])
                    break
    return entradas


def indexar(raiz, ignorar=None):
    """Devolve {"nos": {id: {...}}, "fp": impressão digital do conjunto}."""
    ignorar = ignorar or []
    nos = {}
    if not os.path.isdir(raiz):
        raise SystemExit(f"Pasta do projeto não encontrada: {raiz}")
    for diretorio, subdirs, arquivos in os.walk(raiz):
        subdirs[:] = sorted(d for d in subdirs if d not in PASTAS_PADRAO)
        for nome in sorted(arquivos):
            caminho = os.path.join(diretorio, nome)
            rel = os.path.relpath(caminho, raiz).replace(os.sep, "/")
            if _ignorado(rel, ignorar):
                continue
            try:
                if os.path.getsize(caminho) > MAX_BYTES:
                    continue
                with open(caminho, "rb") as f:
                    bruto = f.read()
                texto = bruto.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # binário ou ilegível
            nos[rel] = {"arquivo": rel, "tipo": "arquivo", "nome": rel,
                        "hash": hashlib.sha256(bruto).hexdigest()[:16]}
            ext = os.path.splitext(nome)[1].lower()
            if ext not in REGEX_POR_EXT:
                continue
            linhas = texto.splitlines()
            usados = {}
            for e in _entradas_arquivo(ext, texto, linhas):
                base = f"{rel}::{e['tipo']}:{e['nome']}"
                usados[base] = usados.get(base, 0) + 1
                nid = base if usados[base] == 1 else f"{base}#{usados[base]}"
                nos[nid] = {"arquivo": rel, "tipo": e["tipo"], "nome": e["nome"],
                            "ini": e["ini"], "fim": e["fim"], "hash": _hash(linhas[e["ini"] - 1:e["fim"]])}
    fp = hashlib.sha256("|".join(f"{i}:{n['hash']}" for i, n in sorted(nos.items())).encode()).hexdigest()[:16]
    return {"nos": nos, "fp": fp}


def trecho(raiz, no, max_linhas=80):
    """Lê o código de um nó direto do disco (usado só quando a IA precisa julgar)."""
    try:
        with open(os.path.join(raiz, no["arquivo"]), encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except OSError:
        return ""
    if no["tipo"] == "arquivo":
        return "\n".join(linhas[:max_linhas])
    return "\n".join(linhas[no["ini"] - 1:min(no["fim"], no["ini"] - 1 + max_linhas)])
