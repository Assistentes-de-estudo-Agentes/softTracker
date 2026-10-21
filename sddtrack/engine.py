"""Motor de sincronização.

Regra central: o status é SEMPRE recalculado a partir do código que existe agora.
Se o código some, a evidência some e a task volta atrás. Nada é "lembrado" sem prova.
"""
import fnmatch
import hashlib
import json
import os
import re
import time

from . import estado as est
from . import indexer, llm, spec as spec_mod, tracegraph, test_runner

SIMBOLOS = {"funcao", "classe", "rota"}


class ErroSpec(Exception):
    pass


# ---------------------------------------------------------------- casamento por padrão (sem IA)
def _norm(s):
    return re.sub(r"[\s_\-]", "", s.lower())


def _glob_ci(valor, padrao):
    """Glob case-insensitive; aceita uma string ou uma lista de alternativas."""
    padroes = padrao if isinstance(padrao, (list, tuple, set)) else [padrao]
    return any(fnmatch.fnmatchcase(str(valor).lower(), str(p).lower()) for p in padroes)


def _escopo(artefato):
    """Normaliza a configuração opcional de escopo de um artefato de conteúdo."""
    bruto = artefato.get("escopo")
    if not bruto:
        return None
    if isinstance(bruto, str):
        return {"tipo": "funcao", "padrao": bruto}
    if isinstance(bruto, dict):
        return {"tipo": bruto.get("tipo", "funcao"), "padrao": bruto.get("padrao", "*")}
    return None


def _candidatos_conteudo(artefato, nos, indices=None):
    """Devolve arquivos ou símbolos em escopo, restringindo a busca ao necessário."""
    indices = indices or {}
    arquivo_padrao = artefato.get("arquivo", "*")
    escopo = _escopo(artefato)
    if not escopo:
        return indices.get("arquivo") or [i for i, n in nos.items() if n.get("tipo") == "arquivo"]

    tipo = escopo["tipo"]
    tipos = SIMBOLOS if tipo == "simbolo" else {tipo}
    ids = []
    for t in tipos:
        ids.extend(indices.get(t) or [i for i, n in nos.items() if n.get("tipo") == t])
    resultado = []
    for nid in ids:
        n = nos.get(nid, {})
        caminho = n.get("arquivo", "")
        if not (_glob_ci(caminho, arquivo_padrao)
                or _glob_ci(os.path.basename(caminho), arquivo_padrao)):
            continue
        if _glob_ci(n.get("nome", ""), escopo["padrao"]):
            resultado.append(nid)
    return sorted(set(resultado))


def casar(artefato, nos, indices=None, raiz=None, cache_conteudo=None):
    """Busca por tipo no índice do grafo, evitando varrer nós irrelevantes."""
    tipo, pad = artefato["tipo"], artefato["padrao"]
    achados = []
    indices = indices or {}
    if tipo in {"arquivo", "conteudo"}:
        candidatos = (_candidatos_conteudo(artefato, nos, indices) if tipo == "conteudo"
                      else (indices.get("arquivo") or [i for i, n in nos.items() if n["tipo"] == "arquivo"]))
    elif tipo == "rota":
        candidatos = indices.get("rota") or [i for i, n in nos.items() if n["tipo"] == "rota"]
    elif tipo in {"funcao", "classe"}:
        candidatos = indices.get(tipo) or [i for i, n in nos.items() if n["tipo"] == tipo]
    else:
        candidatos = [i for t in ("funcao", "classe", "rota") for i in indices.get(t, [])]
        if not candidatos:
            candidatos = [i for i, n in nos.items() if n["tipo"] in SIMBOLOS]
    for nid in candidatos:
        n = nos.get(nid)
        if not n:
            continue
        if tipo == "arquivo":
            ok = fnmatch.fnmatch(n["nome"].lower(), pad.lower())
        elif tipo == "conteudo":
            arquivo_padrao = artefato.get("arquivo", "*")
            caminho = n.get("arquivo", n["nome"])
            if not (_glob_ci(caminho, arquivo_padrao)
                    or _glob_ci(os.path.basename(caminho), arquivo_padrao)):
                ok = False
            else:
                ok = False
                cache_conteudo = cache_conteudo if cache_conteudo is not None else {}
                escopo = _escopo(artefato)
                chave_cache = json.dumps([caminho, n.get("hash"), arquivo_padrao, pad, escopo],
                                         ensure_ascii=False, sort_keys=True)
                if chave_cache in cache_conteudo:
                    ok = cache_conteudo[chave_cache]
                elif raiz:
                    try:
                        with open(os.path.join(raiz, caminho), encoding="utf-8", errors="ignore") as f:
                            conteudo = f.read(indexer.MAX_BYTES + 1)
                        if len(conteudo) <= indexer.MAX_BYTES:
                            ext = os.path.splitext(caminho)[1].lower()
                            conteudo = indexer.sem_comentarios(conteudo, ext)
                            if escopo:
                                linhas = conteudo.splitlines()
                                inicio = max(0, int(n.get("ini", 1)) - 1)
                                fim = min(len(linhas), int(n.get("fim", len(linhas))))
                                conteudo = "\n".join(linhas[inicio:fim])
                            try:
                                ok = re.search(pad, conteudo, re.I | re.M) is not None
                            except re.error:
                                ok = pad.lower() in conteudo.lower()
                    except OSError:
                        ok = False
                    cache_conteudo[chave_cache] = ok
        elif tipo == "rota":
            m = re.match(r"(\w+)\s+(.*)", pad.strip())
            alvo = f"{m.group(1).upper()} {m.group(2)}" if m else pad
            ok = fnmatch.fnmatch(n["nome"], re.sub(r"(:\w+|\{[^}]+\}|<[^>]+>)", "*", alvo))
        else:
            nome = n["nome"]
            ok = fnmatch.fnmatch(_norm(nome), _norm(pad)) or fnmatch.fnmatch(_norm(nome.split(".")[-1]), _norm(pad))
        if ok:
            achados.append(nid)
    return achados


def _ev(nos, ids):
    return [{"no": i, "hash": nos[i]["hash"]} for i in ids]


def _fingerprint_busca(artefato, grafo):
    """Fingerprint somente das entradas relevantes para uma busca determinística.

    Para nome de símbolo/rota, mudança no corpo não altera o resultado da busca;
    para `conteudo`, hash e conjunto dos arquivos candidatos fazem parte do fingerprint.
    """
    tipo = artefato["tipo"]
    padrao = artefato["padrao"]
    nos = grafo.get("nos", {})
    indices = grafo.get("indices") or {}
    if tipo in {"arquivo", "conteudo"}:
        candidatos = (_candidatos_conteudo(artefato, nos, indices) if tipo == "conteudo"
                      else (indices.get("arquivo") or [i for i, n in nos.items() if n.get("tipo") == "arquivo"]))
    elif tipo == "rota":
        candidatos = indices.get("rota") or [i for i, n in nos.items() if n.get("tipo") == "rota"]
    elif tipo in {"funcao", "classe"}:
        candidatos = indices.get(tipo) or [i for i, n in nos.items() if n.get("tipo") == tipo]
    else:
        candidatos = [i for t in ("funcao", "classe", "rota") for i in indices.get(t, [])]
        if not candidatos:
            candidatos = [i for i, n in nos.items() if n.get("tipo") in SIMBOLOS]

    if tipo == "conteudo":
        escopo = _escopo(artefato)
        relevantes = []
        for nid in candidatos:
            n = nos.get(nid, {})
            caminho = n.get("arquivo", n.get("nome", ""))
            relevantes.append((nid, caminho, n.get("hash")))
    elif tipo == "arquivo":
        # O casamento de arquivo usa o nome, não o conteúdo.
        relevantes = [(nid, nos[nid].get("nome", "")) for nid in candidatos if nid in nos]
    else:
        # Rotas/classes/funções são casadas por nome. Hashes do corpo são irrelevantes.
        relevantes = [(nid, nos[nid].get("nome", "")) for nid in candidatos if nid in nos]
    payload = json.dumps([tipo, padrao, relevantes], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _hash_def(c):
    return hashlib.sha256(json.dumps([c.get("descricao"), c.get("artefato"), c.get("usar_ia")],
                                     sort_keys=True).encode()).hexdigest()[:12]


def _catalogo(c, nos, limite=150):
    """Nomes de símbolos ordenados por sobreposição de palavras com o critério (barato, local)."""
    palavras = set(re.findall(r"\w{4,}", c["descricao"].lower()))
    pontuados = []
    for nid, n in nos.items():
        if n["tipo"] in SIMBOLOS:
            pontos = sum(1 for p in palavras if p in nid.lower())
            pontuados.append((-pontos, nid, n["tipo"]))
    pontuados.sort()
    return [(i, t) for _, i, t in pontuados[:limite]]


# ---------------------------------------------------------------- avaliação de um critério
def _avaliar(task, c, prev, grafo, manuais, ctx):
    nos, chave, dh = grafo["nos"], f"{task['id']}/{c['id']}", _hash_def(c)
    rec = {"def_hash": dh, "atendido": False, "origem": "padrao", "evidencia": [], "nivel_evidencia": "nenhuma"}

    if chave in manuais:  # vínculo manual/do agente: nunca sobrescrito pela IA da API
        ids = manuais[chave] if isinstance(manuais[chave], dict) else {i: None for i in manuais[chave]}
        presentes = [i for i in ids if i in nos]
        if len(presentes) < len(ids):
            ctx["avisos"].append(f"{chave}: vínculo aponta para nó que não existe mais")
        rec.update(origem="manual", nivel_evidencia="revisao_manual", atendido=bool(ids) and len(presentes) == len(ids), evidencia=_ev(nos, presentes))
        if rec["atendido"] and any(ids[i] and ids[i] != nos[i]["hash"] for i in presentes):
            rec["revalidar"] = True  # o código vinculado mudou desde que alguém julgou
            _pendente(task, c, ctx, nos, "codigo_mudou", presentes)
        return rec

    art = c.get("artefato")
    if art:
        # Reaproveita julgamento determinístico se todos os nós que o sustentam
        # continuam presentes com os mesmos hashes. Isso evita regex/busca a cada sync.
        ev_antiga = prev.get("evidencia") or []
        if (prev.get("origem") == "padrao" and prev.get("def_hash") == dh and prev.get("atendido") and ev_antiga
                and all(e.get("no") in nos and nos[e["no"]].get("hash") == e.get("hash") for e in ev_antiga)):
            rec.update(atendido=True, evidencia=ev_antiga,
                       nivel_evidencia=prev.get("nivel_evidencia", "estrutural"))
            ctx["criterios_reaproveitados"] = ctx.get("criterios_reaproveitados", 0) + 1
            return rec
        # Cache negativo guiado apenas pelos candidatos que poderiam satisfazer o critério.
        # Mudanças em código não relacionado não disparam a mesma busca novamente.
        fp_busca = _fingerprint_busca(art, grafo)
        if (not c.get("usar_ia") and prev.get("origem") == "padrao" and prev.get("def_hash") == dh
                and prev.get("atendido") is False and prev.get("busca_fp") == fp_busca):
            rec["busca_fp"] = fp_busca
            ctx["criterios_reaproveitados"] = ctx.get("criterios_reaproveitados", 0) + 1
            return rec
        achados = casar(art, nos, grafo.get("indices"), ctx.get("raiz"),
                        ctx.setdefault("cache_conteudo", {}))
        if achados:
            nivel = "textual" if art["tipo"] == "conteudo" else "estrutural"
            rec.update(atendido=True, evidencia=_ev(nos, achados[:5]), nivel_evidencia=nivel)
            return rec
        if not c.get("usar_ia"):
            rec["busca_fp"] = fp_busca
            return rec

    rec["origem"] = "ia"
    anterior = prev if prev.get("origem") == "ia" and prev.get("def_hash") == dh else {}
    ev = anterior.get("evidencia") or []
    if anterior.get("atendido") and ev:
        faltam = [e for e in ev if e["no"] not in nos]
        mudou = [e for e in ev if e["no"] in nos and nos[e["no"]]["hash"] != e["hash"]]
        if not faltam and not mudou:
            rec.update(atendido=True, evidencia=ev, justificativa=anterior.get("justificativa", ""), nivel_evidencia="analise_semantica")
            return rec
        if not faltam:  # código mudou: reavalia se puder, senão marca para revalidar
            if _pode_ia(ctx):
                return _consultar_ia(task, c, rec, grafo, ctx, [e["no"] for e in ev])
            rec.update(atendido=True, evidencia=ev, revalidar=True, justificativa=anterior.get("justificativa", ""))
            _pendente(task, c, ctx, nos, "codigo_mudou", [e["no"] for e in ev])
            return rec
        # parte da evidência foi apagada: perde o vínculo e tenta de novo abaixo

    if anterior.get("ia_fp") == grafo["fp"] and not anterior.get("atendido"):
        rec["ia_fp"] = grafo["fp"]  # nada mudou desde a última tentativa: não gasta IA
        return rec
    if not any(n["tipo"] in SIMBOLOS for n in nos.values()):
        return rec  # sem código ainda: nada a analisar
    if not _pode_ia(ctx):
        _pendente(task, c, ctx, nos, "sem_artefato" if not art else "padrao_nao_achou")
        return rec
    return _consultar_ia(task, c, rec, grafo, ctx, None)


def _fp_cand(ids, nos):
    return hashlib.sha256("|".join(f"{i}:{nos[i]['hash']}" for i in sorted(ids)).encode()).hexdigest()[:12]


def _pendente(task, c, ctx, nos, motivo, ids=None):
    """Registra um critério que precisa de julgamento (feito pelo agente, ex.: Gemini no Antigravity)."""
    cand = ids or [i for i, _ in _catalogo(c, nos, 30)]
    if not cand:
        return
    fp = _fp_cand(cand, nos)
    chave = f"{task['id']}/{c['id']}"
    if ctx["negativos"].get(chave) == fp:
        return  # já julgado como "não feito" e os candidatos não mudaram
    ctx["pendentes"].append({"chave": chave, "task": task["id"], "titulo_task": task.get("titulo", ""),
                             "criterio": c["id"], "descricao": c["descricao"], "motivo": motivo,
                             "candidatos": cand})


def _pode_ia(ctx):
    return ctx["usar_ia"] and llm.disponivel() and ctx["orcamento"] > 0


def _consultar_ia(task, c, rec, grafo, ctx, ids):
    nos = grafo["nos"]
    ctx["orcamento"] -= 1
    try:
        if ids is None:
            ids = [i for i in llm.escolher(task, c, _catalogo(c, nos)) if i in nos][:5]  # IA não inventa nós
        rec["ia_fp"] = grafo["fp"]
        if not ids:
            return rec
        trechos = [(i, indexer.trecho(ctx["raiz"], nos[i])) for i in ids]
        ok, just = llm.julgar(task, c, trechos)
        rec.update(atendido=ok, justificativa=just, evidencia=_ev(nos, ids) if ok else [], nivel_evidencia="analise_semantica" if ok else "nenhuma")
    except Exception as e:  # falha de rede/JSON não derruba o sync
        ctx["avisos"].append(f"{task['id']}/{c['id']}: falha na IA ({e.__class__.__name__})")
    return rec


# ---------------------------------------------------------------- status derivado
def status_task(criterios):
    if any(c.get("revalidar") for c in criterios.values()):
        return "revalidar"
    n = sum(1 for c in criterios.values() if c["atendido"])
    return "feita" if n == len(criterios) and n else ("parcial" if n else "nao_feita")


def _status_agregado(statuses):
    if statuses and all(s == "feita" for s in statuses):
        return "feita"
    if "revalidar" in statuses:
        return "revalidar"
    return "parcial" if any(s in ("feita", "parcial") for s in statuses) else "nao_feita"


def sincronizar(cfg, usar_ia=True, max_ia=20, simular=False):
    spec = spec_mod.carregar(cfg["specs"])
    erros, avisos_spec = spec_mod.validar(spec)
    if erros:
        raise ErroSpec(erros)
    antigo = est.carregar(cfg)
    grafo_antigo = est.carregar_codigo(cfg)
    grafo = indexer.indexar(cfg["projeto"], spec["ignorar"], anterior=grafo_antigo)
    manuais = est.carregar_manuais(cfg)
    ctx = {"avisos": [], "usar_ia": usar_ia, "orcamento": max_ia, "raiz": cfg["projeto"],
           "pendentes": [], "negativos": est.carregar_negativos(cfg), "criterios_reaproveitados": 0,
           "cache_conteudo": {}}

    tasks = {}
    for t in spec["tasks"]:
        prev_t = (antigo.get("tasks", {}).get(t["id"]) or {}).get("criterios", {})
        crits = {c["id"]: _avaliar(t, c, prev_t.get(c["id"], {}), grafo, manuais, ctx) for c in t["criterios"]}
        tasks[t["id"]] = {"titulo": t.get("titulo", ""), "depende_de": t["depende_de"],
                          "caso_de_uso": t.get("caso_de_uso"), "casos_de_uso": t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else []),
                          "status": status_task(crits), "criterios": crits,
                          "descricoes": {c["id"]: c["descricao"] for c in t["criterios"]}}
        if tasks[t["id"]]["status"] == "feita":
            for d in t["depende_de"]:
                if d in tasks and tasks[d]["status"] != "feita":
                    ctx["avisos"].append(f"{t['id']} está feita mas depende de {d} ({tasks[d]['status']})")

    armazenamento_testes = est.carregar_testes(cfg)
    validacao_testes, fingerprints_testes = test_runner.aplicar_validacao(
        spec, tasks, grafo, armazenamento_testes, cfg)

    usados = {e["no"].split("::")[0] for t in tasks.values() for c in t["criterios"].values() for e in c["evidencia"]}
    arquivos_codigo = sorted({n["arquivo"] for n in grafo["nos"].values() if n["tipo"] in SIMBOLOS})
    total_crit = sum(len(t["criterios"]) for t in tasks.values())
    ok_crit = sum(1 for t in tasks.values() for c in t["criterios"].values() if c["atendido"])
    feitas = sum(1 for t in tasks.values() if t["status"] == "feita")
    contagem = {s: sum(1 for t in tasks.values() if t["status"] == s)
                for s in ("feita", "parcial", "nao_feita", "revalidar")}

    novo = {
        "projeto": spec.get("projeto", ""), "ultimo_sync": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "spec_hash": spec["hash"], "codigo_fp": grafo["fp"],
        "resumo": {"tasks_total": len(tasks), "tasks_feitas": feitas, "por_status": contagem,
                   "progresso_tasks": round(feitas / len(tasks), 4) if tasks else 0,
                   "criterios_total": total_crit, "criterios_atendidos": ok_crit,
                   "progresso_criterios": round(ok_crit / total_crit, 4) if total_crit else 0,
                   "arquivos": sum(1 for n in grafo["nos"].values() if n["tipo"] == "arquivo"),
                   "nos_de_codigo": sum(1 for n in grafo["nos"].values() if n["tipo"] in SIMBOLOS)},
        "tasks": tasks,
        "validacao_testes": validacao_testes,
        "grafo_tasks": {"nos": [{"id": i, "titulo": t["titulo"], "status": t["status"]} for i, t in tasks.items()],
                        "arestas": [[d, i] for i, t in tasks.items() for d in t["depende_de"]]},
        "requisitos": _por_requisito(spec, tasks),
        "casos_de_uso": _por_caso_de_uso(spec, tasks),
        "tasks_sem_caso_de_uso": [i for i, t in tasks.items() if not t["caso_de_uso"]],
        "stack": spec["stack"],
        "uml": [{"id": e["id"], "tipo": e.get("tipo"), "elemento": e.get("elemento"), "tasks": e.get("tasks") or [],
                 "status": _status_agregado([tasks[x]["status"] for x in (e.get("tasks") or [])])}
                for e in spec["uml"]],
        "codigo_sem_task": [a for a in arquivos_codigo if a not in usados],
        "pendentes_ia": ctx["pendentes"], "avisos": ctx["avisos"], "avisos_spec": avisos_spec, "ia_usada": max_ia - ctx["orcamento"],
        "indexacao": {**grafo.get("_estatisticas_indexacao", {}),
                      "criterios_reaproveitados": ctx.get("criterios_reaproveitados", 0)},
    }
    grafo_rastreabilidade_anterior = antigo.get("grafo_rastreabilidade", {})
    novo["grafo_rastreabilidade"] = tracegraph.construir(
        spec, tasks, grafo, ctx["pendentes"], validacao_testes.get("testes", {}))
    diff = grafo.get("_diff", {})
    codigos_alterados = sorted(set(diff.get("adicionados", []) + diff.get("alterados", []) + diff.get("removidos", [])))
    novo["impacto_codigo"] = tracegraph.impacto(novo["grafo_rastreabilidade"], grafo_rastreabilidade_anterior, codigos_alterados)
    mudancas = [f"{i}: {antigo['tasks'][i]['status'] if i in antigo.get('tasks', {}) else '(nova)'} → {t['status']}"
                for i, t in tasks.items()
                if (antigo.get("tasks", {}).get(i) or {}).get("status") != t["status"]]
    novo["mudancas"] = mudancas
    if not simular:
        est.salvar(cfg, novo, grafo)
    return novo


def _por_caso_de_uso(spec, tasks):
    saida = []
    for u in spec["casos_de_uso"]:
        ts = [i for i, t in tasks.items() if u["id"] in (t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else []))]
        feitas = sum(1 for x in ts if tasks[x]["status"] == "feita")
        saida.append({"id": u["id"], "titulo": u.get("titulo", ""), "descricao": u.get("descricao", ""),
                      "requisitos": u.get("requisitos") or [], "tasks": ts, "feitas": feitas, "total": len(ts),
                      "status": _status_agregado([tasks[x]["status"] for x in ts])})
    return saida


def _por_requisito(spec, tasks):
    saida = []
    for r in spec["requisitos"]:
        ucs = [u["id"] for u in spec["casos_de_uso"] if r["id"] in (u.get("requisitos") or [])]
        ts = [t["id"] for t in spec["tasks"]
              if ucs and (t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else []))
              and any(uc_id in ucs for uc_id in (t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else [])))]
        saida.append({"id": r["id"], "titulo": r.get("titulo", ""), "casos_de_uso": ucs, "tasks": ts,
                      "status": _status_agregado([tasks[x]["status"] for x in ts])})
    return saida
