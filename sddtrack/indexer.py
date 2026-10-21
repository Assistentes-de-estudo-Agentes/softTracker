"""Indexa a pasta do projeto em um grafo de nós (arquivo, função, classe, rota) com hash.

Sem dependências externas e sem IA. Tolera código incompleto (projeto em construção):
se o arquivo Python não compila, usa expressões regulares no lugar do `ast`.
"""
import ast
import fnmatch
import hashlib
import os
import re
import json

PASTAS_PADRAO = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                 ".idea", ".vscode", ".next", "target", ".pytest_cache"}
MAX_BYTES = 800_000
MAX_LINHAS_NO = 120

_JS = [("funcao", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"),
       ("classe", r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"),
       ("funcao", r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>")]
_JAVA = [("classe", r"\b(?:class|interface|enum|record)\s+(\w+)"),
         ("funcao", r"^\s*(?:public|private|protected|internal|static|final|async|override|\s)+[\w<>\[\],.? ]+\s+(\w+)\s*\([^;{]*\)\s*(?:throws [\w, .]+)?\s*(?:\{.*)?$"),
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


def sem_comentarios(texto, ext):
    """Remove comentários preservando linhas, offsets e literais de código.

    Preservar strings é necessário para reconhecer caminhos declarados em anotações
    Spring e chamadas de rota. Comentários viram espaços, mas quebras de linha ficam.
    """
    ext = (ext or "").lower()
    barras = ext in {".java", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue",
                     ".svelte", ".kt", ".cs", ".go", ".php", ".rs", ".c", ".h", ".cc",
                     ".cpp", ".hpp", ".swift", ".scala", ".groovy", ".dart"}
    cerquilha = ext in {".py", ".rb", ".yml", ".yaml", ".toml", ".sh", ".properties",
                       ".r", ".pl", ".pm", ".ex", ".exs"}
    if not barras and not cerquilha:
        return texto

    saida = list(texto)
    n = len(texto)
    i = 0
    estado = "normal"
    while i < n:
        ch = texto[i]
        prox = texto[i + 1] if i + 1 < n else ""

        if estado == "linha_comentario":
            if ch in "\r\n":
                estado = "normal"
            else:
                saida[i] = " "
            i += 1
            continue

        if estado == "bloco_comentario":
            if ch == "*" and prox == "/":
                saida[i] = saida[i + 1] = " "
                i += 2
                estado = "normal"
                continue
            if ch not in "\r\n":
                saida[i] = " "
            i += 1
            continue

        if estado in {"string_simples", "string_dupla", "template", "tripla_simples", "tripla_dupla"}:
            if ch == "\\\\":
                i += 2
                continue
            if estado == "tripla_simples" and texto.startswith(chr(39) * 3, i):
                i += 3
                estado = "normal"
                continue
            if estado == "tripla_dupla" and texto.startswith(chr(34) * 3, i):
                i += 3
                estado = "normal"
                continue
            if estado == "string_simples" and ch == "'":
                estado = "normal"
            elif estado == "string_dupla" and ch == '"':
                estado = "normal"
            elif estado == "template" and ch == "`":
                estado = "normal"
            i += 1
            continue

        if ext == ".py" and texto.startswith(chr(39) * 3, i):
            estado = "tripla_simples"
            i += 3
            continue
        if ext in {".py", ".java", ".kt"} and texto.startswith(chr(34) * 3, i):
            estado = "tripla_dupla"
            i += 3
            continue
        if ch == "'":
            estado = "string_simples"
            i += 1
            continue
        if ch == '"':
            estado = "string_dupla"
            i += 1
            continue
        if ch == "`" and ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".go"}:
            estado = "template"
            i += 1
            continue
        if barras and ch == "/" and prox == "/":
            saida[i] = saida[i + 1] = " "
            estado = "linha_comentario"
            i += 2
            continue
        if barras and ch == "/" and prox == "*":
            saida[i] = saida[i + 1] = " "
            estado = "bloco_comentario"
            i += 2
            continue
        if cerquilha and ch == "#":
            saida[i] = " "
            estado = "linha_comentario"
            i += 1
            continue
        i += 1
    return "".join(saida)

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


def _chamadas_no_escopo(texto):
    """Nomes de chamadas diretas no escopo; é uma relação potencial, não análise de tipos."""
    palavras_chave = {"if", "for", "while", "switch", "catch", "function", "return", "new",
                      "typeof", "delete", "throw", "await", "yield", "super", "class", "def",
                      "with", "try", "except", "elif", "assert", "import", "from", "print"}
    # Inclui chamadas qualificadas (this.foo(), service.buscar(), etc.). É uma
    # relação potencial por nome; não pretende resolver tipos nem despacho dinâmico.
    nomes = set(re.findall(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*\(", texto))
    return sorted(n for n in nomes if n not in palavras_chave)


def _normalizar_rota(metodo, caminho):
    caminho = re.sub(r"(:\w+|\{[^}]+\}|<[^>]+>)", "*", caminho.strip()) or "/"
    if not caminho.startswith("/"):
        caminho = "/" + caminho
    if len(caminho) > 1:
        caminho = caminho.rstrip("/")
    return f"{metodo.upper()} {caminho}"


def _argumento_caminho(argumentos):
    """Extrai value/path ou o primeiro literal de uma anotação Spring."""
    if not argumentos:
        return ""
    m = re.search(r"\b(?:value|path)\s*=\s*(?:\{\s*)?['\"]([^'\"]*)['\"]", argumentos)
    if m:
        return m.group(1)
    m = re.search(r"['\"]([^'\"]*)['\"]", argumentos)
    return m.group(1) if m else ""


def _prefixo_controller_java(texto):
    """Lê @RequestMapping da classe para compor rotas de métodos Spring."""
    for m in re.finditer(r"@RequestMapping\b\s*(?:\((.*?)\))?", texto, re.S):
        # A anotação de classe costuma anteceder a declaração de class; não confundir
        # com @RequestMapping de método.
        resto = texto[m.end():m.end() + 260]
        classe = re.search(r"\bclass\s+\w+", resto)
        outro_metodo = re.search(r"\b(?:public|private|protected)\s+[\w<>,.?\[\] ]+\s+\w+\s*\(", resto)
        if classe and (not outro_metodo or classe.start() < outro_metodo.start()):
            return _argumento_caminho(m.group(1) or "")
    return ""


def _entradas_rotas_java(texto):
    """Reconhece anotações Spring e combina o prefixo do controller com o caminho."""
    prefixo = _prefixo_controller_java(texto).strip()
    saida = []
    rx = re.compile(r"@(Get|Post|Put|Delete|Patch)Mapping\b\s*(?:\((.*?)\))?", re.I | re.S)
    for m in rx.finditer(texto):
        metodo = m.group(1).upper()
        caminho = _argumento_caminho(m.group(2) or "").strip()
        if prefixo and caminho:
            caminho = prefixo.rstrip("/") + "/" + caminho.lstrip("/")
        elif prefixo:
            caminho = prefixo
        elif not caminho:
            caminho = "/"
        linha = texto.count("\n", 0, m.start()) + 1
        saida.append({"tipo": "rota", "nome": _normalizar_rota(metodo, caminho),
                      "ini": linha, "rota": True})
    # @RequestMapping com método explícito é comum em controllers mais antigos.
    rx_request = re.compile(r"@RequestMapping\s*\((.*?)\)", re.S)
    prefix_start = None
    for m in rx_request.finditer(texto):
        if _prefixo_controller_java(texto) == _argumento_caminho(m.group(1) or ""):
            continue  # anotação da classe, já usada como prefixo
        args = m.group(1) or ""
        met = re.search(r"RequestMethod\.(GET|POST|PUT|DELETE|PATCH)", args, re.I)
        if not met:
            continue
        caminho = _argumento_caminho(args) or "/"
        if prefixo and caminho != prefixo:
            caminho = prefixo.rstrip("/") + "/" + caminho.lstrip("/")
        saida.append({"tipo": "rota", "nome": _normalizar_rota(met.group(1), caminho),
                      "ini": texto.count("\n", 0, m.start()) + 1, "rota": True})
    return saida


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


def _alvo_rota_javascript(linha):
    """Extrai o handler nomeado de declarações Express/Node em uma única linha."""
    m = re.search(
        r"\b(?:app|router|server|route|api|bp|blueprint)\w*\."
        r"(?:get|post|put|delete|patch)\s*\(\s*['\"`][^'\"`]+['\"`]\s*,\s*"
        r"(?:async\s*)?([A-Za-z_$][\w$]*)\s*(?=[,)])",
        linha, re.I,
    )
    return m.group(1) if m else None


def _fim_bloco_com_chaves(texto, linha_inicio):
    """Localiza a chave de fechamento do bloco de função, ignorando chaves em strings.

    O texto recebido já teve comentários mascarados. Retorna a linha final ou None
    quando a função não usa um bloco com chaves (por exemplo, arrow expression).
    """
    linhas = texto.splitlines(keepends=True)
    inicio = sum(len(linha) for linha in linhas[:max(0, linha_inicio - 1)])
    estado = "normal"
    quote = ""
    profundidade = 0
    comeco_bloco = False
    i = inicio
    n = len(texto)
    while i < n:
        ch = texto[i]
        prox = texto[i + 1] if i + 1 < n else ""
        if estado == "string":
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                estado = "normal"
            i += 1
            continue
        if estado == "tripla":
            if texto.startswith(quote * 3, i):
                i += 3
                estado = "normal"
                continue
            if ch == "\\":
                i += 2
                continue
            i += 1
            continue
        if ch in ("'", '"', "`"):
            if ch != "`" and texto.startswith(ch * 3, i):
                quote = ch
                estado = "tripla"
                i += 3
            else:
                quote = ch
                estado = "string"
                i += 1
            continue
        if ch == "{" :
            profundidade += 1
            comeco_bloco = True
        elif ch == "}" and comeco_bloco:
            profundidade -= 1
            if profundidade == 0:
                return texto.count("\n", 0, i) + 1
        i += 1
    return None


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
    if ext in {".java", ".kt"}:
        entradas.extend(_entradas_rotas_java(texto))
    else:
        for i, linha in enumerate(linhas, 1):
            for rx, extrair in ROTAS:
                m = rx.search(linha)
                if m:
                    metodo, caminho = extrair(m)
                    entrada_rota = {"tipo": "rota", "nome": _normalizar_rota(metodo, caminho), "ini": i, "rota": True}
                    if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                        alvo = _alvo_rota_javascript(linha)
                        if alvo:
                            entrada_rota["alvo"] = alvo
                    entradas.append(entrada_rota)
                    break
    # Para linguagens com blocos de chaves, delimita funções pelo fechamento real do
    # bloco. Isso impede que código entre duas declarações (como app.get(...)) passe
    # a fazer parte do hash/chamadas da função anterior.
    linguagens_com_chaves = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue",
                            ".svelte", ".java", ".kt", ".cs", ".go", ".php", ".rs", ".c",
                            ".h", ".cc", ".cpp", ".hpp", ".swift", ".scala", ".groovy", ".dart"}
    if ext in linguagens_com_chaves:
        for e in entradas:
            if e["tipo"] == "funcao":
                fim_bloco = _fim_bloco_com_chaves(texto, e["ini"])
                if fim_bloco is not None:
                    e["fim"] = fim_bloco

    # Faixas de fallback para símbolos reconhecidos por regex sem bloco delimitável.
    inicios = sorted({e["ini"] for e in entradas})
    for e in entradas:
        if "fim" not in e:
            seguintes = [x for x in inicios if x > e["ini"]]
            limite = (seguintes[0] - 1) if seguintes else len(linhas)
            e["fim"] = max(e["ini"], min(limite, e["ini"] + MAX_LINHAS_NO - 1))

    # Somente anotações/decoradores antecedentes herdam a faixa do método. Uma
    # chamada JS app.get(...) é um registro de rota, não um decorador do próximo símbolo.
    funcoes = [f for f in entradas if f["tipo"] == "funcao"]
    if ext in {".java", ".kt", ".py", ".cs"}:
        for e in entradas:
            if e.get("rota"):
                for f in funcoes:
                    if 0 <= f["ini"] - e["ini"] <= 3:
                        e["fim"] = max(e["fim"], f["fim"])
                        break
    return entradas


def indexar(raiz, ignorar=None, anterior=None):
    """Indexa o projeto e reaproveita nós de arquivos que não mudaram.

    O cache usa caminho + tamanho + mtime_ns + inode. Assim, em um sync repetido,
    a pasta continua sendo percorrida, mas o conteúdo e os símbolos de arquivos
    inalterados não precisam ser lidos/analisados novamente.
    """
    ignorar = ignorar or []
    anterior = anterior or {}
    nos_antigos = anterior.get("nos", {}) if isinstance(anterior, dict) else {}
    arquivos_antigos = anterior.get("_arquivos", {}) if isinstance(anterior, dict) else {}
    config_hash = hashlib.sha256(json.dumps({"ignorar": sorted(ignorar), "parser": 6},
                                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    cache_valido = anterior.get("_indexador_config") == config_hash
    nos = {}
    arquivos_cache = {}
    contagem = {"arquivos_lidos": 0, "arquivos_reutilizados": 0, "nos_reutilizados": 0}
    if not os.path.isdir(raiz):
        raise SystemExit(f"Pasta do projeto não encontrada: {raiz}")

    for diretorio, subdirs, arquivos in os.walk(raiz):
        subdirs[:] = sorted(d for d in subdirs if d not in PASTAS_PADRAO and not d.startswith("."))
        for nome in sorted(arquivos):
            caminho = os.path.join(diretorio, nome)
            rel = os.path.relpath(caminho, raiz).replace(os.sep, "/")
            if _ignorado(rel, ignorar):
                continue
            try:
                st = os.stat(caminho)
            except OSError:
                continue
            metadados = {"mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
                         "size": st.st_size, "inode": getattr(st, "st_ino", 0)}
            entrada_antiga = arquivos_antigos.get(rel, {})
            ids_antigos = entrada_antiga.get("nos", [])
            if (cache_valido and entrada_antiga.get("mtime_ns") == metadados["mtime_ns"]
                    and entrada_antiga.get("size") == metadados["size"]
                    and entrada_antiga.get("inode", 0) == metadados["inode"]
                    and ids_antigos and all(nid in nos_antigos for nid in ids_antigos)):
                for nid in ids_antigos:
                    nos[nid] = nos_antigos[nid]
                arquivos_cache[rel] = {**metadados, "nos": ids_antigos}
                contagem["arquivos_reutilizados"] += 1
                contagem["nos_reutilizados"] += len(ids_antigos)
                continue
            if st.st_size > MAX_BYTES:
                continue
            try:
                with open(caminho, "rb") as f:
                    bruto = f.read()
                texto = bruto.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            contagem["arquivos_lidos"] += 1
            ids_arquivo = []
            nos[rel] = {"arquivo": rel, "tipo": "arquivo", "nome": rel,
                        "hash": hashlib.sha256(bruto).hexdigest()[:16]}
            ids_arquivo.append(rel)
            ext = os.path.splitext(nome)[1].lower()
            texto_indexavel = sem_comentarios(texto, ext)
            if ext in REGEX_POR_EXT:
                linhas = texto_indexavel.splitlines()
                usados = {}
                for e in _entradas_arquivo(ext, texto_indexavel, linhas):
                    base = f"{rel}::{e['tipo']}:{e['nome']}"
                    usados[base] = usados.get(base, 0) + 1
                    nid = base if usados[base] == 1 else f"{base}#{usados[base]}"
                    linhas_no = linhas[e["ini"] - 1:e["fim"]]
                    no_codigo = {"arquivo": rel, "tipo": e["tipo"], "nome": e["nome"],
                                 "ini": e["ini"], "fim": e["fim"], "hash": _hash(linhas_no)}
                    if e["tipo"] == "funcao":
                        no_codigo["chamadas"] = _chamadas_no_escopo("\n".join(linhas_no))
                    if e.get("alvo"):
                        no_codigo["alvo"] = e["alvo"]
                    nos[nid] = no_codigo
                    ids_arquivo.append(nid)
            arquivos_cache[rel] = {**metadados, "nos": ids_arquivo}

    fp = hashlib.sha256("|".join(f"{i}:{n['hash']}" for i, n in sorted(nos.items())).encode()).hexdigest()[:16]
    anteriores = nos_antigos
    ids_anteriores, ids_atuais = set(anteriores), set(nos)
    adicionados = sorted(ids_atuais - ids_anteriores)
    removidos = sorted(ids_anteriores - ids_atuais)
    alterados = sorted(i for i in ids_atuais & ids_anteriores if nos[i].get("hash") != anteriores[i].get("hash"))

    # Índice por tipo deixa o casamento de critérios mais barato que percorrer todo o grafo.
    indice_tipos = {}
    for nid, no in nos.items():
        indice_tipos.setdefault(no["tipo"], []).append(nid)
    for ids in indice_tipos.values():
        ids.sort()

    # Arestas do grafo sintático: símbolo pertence a um arquivo; rota aponta ao método.
    arestas = []
    por_arquivo = {}
    for nid, no in nos.items():
        if no["tipo"] != "arquivo":
            arestas.append({"de": nid, "para": no["arquivo"], "tipo": "pertence_a"})
            por_arquivo.setdefault(no["arquivo"], []).append((nid, no))
    for rel, entradas in por_arquivo.items():
        funcoes = [(nid, no) for nid, no in entradas if no["tipo"] == "funcao"]
        for nid, no in entradas:
            if no["tipo"] != "rota":
                continue
            alvo = no.get("alvo")
            if alvo:
                handlers = [(fnid, fn) for fnid, fn in funcoes if fn.get("nome") == alvo]
                for fnid, _fn in handlers:
                    arestas.append({"de": nid, "para": fnid, "tipo": "mapeia_para"})
                if handlers:
                    continue
            # Fallback conservador para anotações Java/Spring e rotas embutidas
            # imediatamente antes do método, onde o nome do handler não está na rota.
            possiveis = [(abs(fn.get("ini", 0) - no.get("ini", 0)), fnid)
                         for fnid, fn in funcoes if fn.get("ini", 0) >= no.get("ini", 0)]
            if possiveis:
                distancia, fnid = min(possiveis)
                if distancia <= 5:
                    arestas.append({"de": nid, "para": fnid, "tipo": "mapeia_para"})

    # Grafo de chamadas potencial. O índice armazena nomes de chamadas diretas por função;
    # assim, símbolos inalterados também ganham arestas quando uma função-alvo é adicionada.
    funcoes_por_nome = {}
    for nid, item in nos.items():
        if item.get("tipo") == "funcao":
            funcoes_por_nome.setdefault(item.get("nome", ""), []).append(nid)
    for caller_id, caller in nos.items():
        if caller.get("tipo") != "funcao":
            continue
        for nome_chamado in caller.get("chamadas", []):
            for callee_id in funcoes_por_nome.get(nome_chamado, []):
                if callee_id != caller_id:
                    arestas.append({"de": caller_id, "para": callee_id, "tipo": "chama"})

    return {"nos": nos, "fp": fp, "arestas": arestas, "indices": indice_tipos,
            "_arquivos": arquivos_cache, "_indexador_config": config_hash,
            "_estatisticas_indexacao": contagem,
            "_diff": {"adicionados": adicionados, "alterados": alterados, "removidos": removidos}}


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
