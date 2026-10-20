"""Motor de sincronização.

Regra central: o status é SEMPRE recalculado a partir do código que existe agora.
Se o código some, a evidência some e a task volta atrás. Nada é "lembrado" sem prova.
"""
import fnmatch
import hashlib
import json
import re
import time

from . import estado as est
from . import indexer, llm, spec as spec_mod

SIMBOLOS = {"funcao", "classe", "rota"}


class ErroSpec(Exception):
    pass


# ---------------------------------------------------------------- casamento por padrão (sem IA)
def _norm(s):
    return re.sub(r"[\s_\-]", "", s.lower())


def casar(artefato, nos):
    tipo, pad = artefato["tipo"], artefato["padrao"]
    achados = []
    for nid, n in nos.items():
        if tipo == "arquivo":
            ok = n["tipo"] == "arquivo" and fnmatch.fnmatch(n["nome"].lower(), pad.lower())
        elif tipo == "rota":
            if n["tipo"] != "rota":
                continue
            m = re.match(r"(\w+)\s+(.*)", pad.strip())
            alvo = f"{m.group(1).upper()} {m.group(2)}" if m else pad
            ok = fnmatch.fnmatch(n["nome"], re.sub(r"(:\w+|\{[^}]+\}|<[^>]+>)", "*", alvo))
        else:
            if n["tipo"] == "arquivo" or (tipo != "simbolo" and n["tipo"] != tipo):
                continue
            nome = n["nome"]
            ok = fnmatch.fnmatch(_norm(nome), _norm(pad)) or fnmatch.fnmatch(_norm(nome.split(".")[-1]), _norm(pad))
        if ok:
            achados.append(nid)
    return achados


def _ev(nos, ids):
    return [{"no": i, "hash": nos[i]["hash"]} for i in ids]


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
    rec = {"def_hash": dh, "atendido": False, "origem": "padrao", "evidencia": []}

    if chave in manuais:  # vínculo manual/do agente: nunca sobrescrito pela IA da API
        ids = manuais[chave] if isinstance(manuais[chave], dict) else {i: None for i in manuais[chave]}
        presentes = [i for i in ids if i in nos]
        if len(presentes) < len(ids):
            ctx["avisos"].append(f"{chave}: vínculo aponta para nó que não existe mais")
        rec.update(origem="manual", atendido=bool(ids) and len(presentes) == len(ids), evidencia=_ev(nos, presentes))
        if rec["atendido"] and any(ids[i] and ids[i] != nos[i]["hash"] for i in presentes):
            rec["revalidar"] = True  # o código vinculado mudou desde que alguém julgou
            _pendente(task, c, ctx, nos, "codigo_mudou", presentes)
        return rec

    art = c.get("artefato")
    if art:
        achados = casar(art, nos)
        if achados:
            rec.update(atendido=True, evidencia=_ev(nos, achados[:5]))
            return rec
        if not c.get("usar_ia"):
            return rec

    rec["origem"] = "ia"
    anterior = prev if prev.get("origem") == "ia" and prev.get("def_hash") == dh else {}
    ev = anterior.get("evidencia") or []
    if anterior.get("atendido") and ev:
        faltam = [e for e in ev if e["no"] not in nos]
        mudou = [e for e in ev if e["no"] in nos and nos[e["no"]]["hash"] != e["hash"]]
        if not faltam and not mudou:
            rec.update(atendido=True, evidencia=ev, justificativa=anterior.get("justificativa", ""))
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
        rec.update(atendido=ok, justificativa=just, evidencia=_ev(nos, ids) if ok else [])
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
    grafo = indexer.indexar(cfg["projeto"], spec["ignorar"])
    antigo = est.carregar(cfg)
    manuais = est.carregar_manuais(cfg)
    ctx = {"avisos": [], "usar_ia": usar_ia, "orcamento": max_ia, "raiz": cfg["projeto"],
           "pendentes": [], "negativos": est.carregar_negativos(cfg)}

    tasks = {}
    for t in spec["tasks"]:
        prev_t = (antigo.get("tasks", {}).get(t["id"]) or {}).get("criterios", {})
        crits = {c["id"]: _avaliar(t, c, prev_t.get(c["id"], {}), grafo, manuais, ctx) for c in t["criterios"]}
        tasks[t["id"]] = {"titulo": t.get("titulo", ""), "depende_de": t["depende_de"],
                          "caso_de_uso": t.get("caso_de_uso"), "status": status_task(crits), "criterios": crits,
                          "descricoes": {c["id"]: c["descricao"] for c in t["criterios"]}}
        if tasks[t["id"]]["status"] == "feita":
            for d in t["depende_de"]:
                if d in tasks and tasks[d]["status"] != "feita":
                    ctx["avisos"].append(f"{t['id']} está feita mas depende de {d} ({tasks[d]['status']})")

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
        "grafo_tasks": {"nos": [{"id": i, "titulo": t["titulo"], "status": t["status"]} for i, t in tasks.items()],
                        "arestas": [[d, i] for i, t in tasks.items() for d in t["depende_de"]]},
        "requisitos": _por_requisito(spec, tasks),
        "uml": [{"id": e["id"], "tipo": e.get("tipo"), "elemento": e.get("elemento"), "tasks": e.get("tasks") or [],
                 "status": _status_agregado([tasks[x]["status"] for x in (e.get("tasks") or [])])}
                for e in spec["uml"]],
        "codigo_sem_task": [a for a in arquivos_codigo if a not in usados],
        "pendentes_ia": ctx["pendentes"], "avisos": ctx["avisos"], "avisos_spec": avisos_spec, "ia_usada": max_ia - ctx["orcamento"],
    }
    mudancas = [f"{i}: {antigo['tasks'][i]['status'] if i in antigo.get('tasks', {}) else '(nova)'} → {t['status']}"
                for i, t in tasks.items()
                if (antigo.get("tasks", {}).get(i) or {}).get("status") != t["status"]]
    novo["mudancas"] = mudancas
    if not simular:
        est.salvar(cfg, novo, grafo)
    return novo


def _por_requisito(spec, tasks):
    saida = []
    for r in spec["requisitos"]:
        ucs = [u["id"] for u in spec["casos_de_uso"] if r["id"] in (u.get("requisitos") or [])]
        ts = [t["id"] for t in spec["tasks"] if t.get("caso_de_uso") in ucs]
        saida.append({"id": r["id"], "titulo": r.get("titulo", ""), "casos_de_uso": ucs, "tasks": ts,
                      "status": _status_agregado([tasks[x]["status"] for x in ts])})
    return saida
