"""Carrega e valida o manifesto de especificação (YAML ou JSON, um ou vários arquivos)."""
import hashlib
import json
from graphlib import CycleError, TopologicalSorter

TIPOS_ARTEFATO = {"rota", "funcao", "classe", "arquivo", "simbolo"}
PALAVRAS_VAGAS = ("seguro", "rápido", "rapido", "adequado", "amigável", "amigavel",
                  "fácil", "facil", "performático", "performatico", "robusto", "escalável")


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        texto = f.read()
    if caminho.lower().endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError:
            raise SystemExit("Para ler YAML instale: pip install pyyaml (ou escreva a spec em JSON).")
        return (yaml.safe_load(texto) or {}), texto
    return json.loads(texto), texto


def _normalizar_stack(bruto):
    """Aceita lista de {camada, itens}, dict camada -> itens, ou lista simples. Itens: texto ou {nome, uso}."""
    if not bruto:
        return []
    if isinstance(bruto, dict):
        bruto = [{"camada": k, "itens": v} for k, v in bruto.items()]
    if not isinstance(bruto, list):
        return []
    grupos = []
    for g in bruto:
        if isinstance(g, str):
            g = {"camada": "Stack", "itens": [g]}
        itens = []
        for i in (g.get("itens") or []):
            if isinstance(i, str):
                i = {"nome": i}
            if i.get("nome"):
                itens.append({"nome": str(i["nome"]), "uso": str(i.get("uso", ""))})
        grupos.append({"camada": str(g.get("camada", "Stack")), "itens": itens})
    return grupos


def carregar(caminhos):
    spec = {"requisitos": [], "casos_de_uso": [], "uml": [], "tasks": [], "ignorar": [], "stack": []}
    h = hashlib.sha256()
    for c in caminhos:
        dados, texto = _ler(c)
        h.update(texto.encode("utf-8"))
        for chave in spec:
            if chave == "stack":
                spec["stack"].extend(_normalizar_stack(dados.get("stack")))
            else:
                spec[chave].extend(dados.get(chave) or [])
        if dados.get("projeto"):
            spec["projeto"] = dados["projeto"]
    spec["hash"] = h.hexdigest()
    for t in spec["tasks"]:
        t["depende_de"] = t.get("depende_de") or []
        criterios = []
        for i, c in enumerate(t.get("criterios") or [], 1):
            if isinstance(c, str):
                c = {"descricao": c}
            c.setdefault("id", f"C{i}")
            criterios.append(c)
        t["criterios"] = criterios
    return spec


def validar(spec):
    """Retorna (erros, avisos). Erros bloqueiam a execução; avisos apenas informam."""
    erros, avisos = [], []
    ids = {}
    for tipo in ("requisitos", "casos_de_uso", "uml", "tasks"):
        for item in spec[tipo]:
            i = item.get("id")
            if not i:
                erros.append(f"Item sem id em '{tipo}': {item}")
            elif i in ids:
                erros.append(f"ID duplicado: {i}")
            else:
                ids[i] = tipo
    reqs = {r["id"] for r in spec["requisitos"] if r.get("id")}
    ucs = {u["id"] for u in spec["casos_de_uso"] if u.get("id")}
    tasks = {t["id"] for t in spec["tasks"] if t.get("id")}

    for u in spec["casos_de_uso"]:
        for r in u.get("requisitos") or []:
            if r not in reqs:
                erros.append(f"{u.get('id')}: requisito inexistente '{r}'")
    for el in spec["uml"]:
        for t in el.get("tasks") or []:
            if t not in tasks:
                erros.append(f"{el.get('id')}: task inexistente '{t}'")
    grafo = {}
    for t in spec["tasks"]:
        tid = t.get("id")
        if t.get("caso_de_uso") and t["caso_de_uso"] not in ucs:
            erros.append(f"{tid}: caso de uso inexistente '{t['caso_de_uso']}'")
        for d in t["depende_de"]:
            if d not in tasks:
                erros.append(f"{tid}: dependência inexistente '{d}'")
            if d == tid:
                erros.append(f"{tid}: depende de si mesma")
        grafo[tid] = {d for d in t["depende_de"] if d in tasks}
        if not t["criterios"]:
            erros.append(f"{tid}: task sem critérios de aceite")
        vistos = set()
        for c in t["criterios"]:
            if c["id"] in vistos:
                erros.append(f"{tid}: critério duplicado '{c['id']}'")
            vistos.add(c["id"])
            if not (c.get("descricao") or "").strip():
                erros.append(f"{tid}/{c['id']}: critério sem descrição")
            art = c.get("artefato")
            if art:
                if art.get("tipo") not in TIPOS_ARTEFATO:
                    erros.append(f"{tid}/{c['id']}: tipo de artefato inválido '{art.get('tipo')}'")
                if not art.get("padrao"):
                    erros.append(f"{tid}/{c['id']}: artefato sem padrão")
            else:
                avisos.append(f"{tid}/{c['id']}: sem artefato esperado (só a IA consegue vincular)")
            if any(p in c.get("descricao", "").lower() for p in PALAVRAS_VAGAS) and not art:
                avisos.append(f"{tid}/{c['id']}: critério possivelmente vago")
    try:
        list(TopologicalSorter(grafo).static_order())
    except CycleError as e:
        erros.append(f"Ciclo nas dependências: {' -> '.join(map(str, e.args[1]))}")

    if not any(g["itens"] for g in spec["stack"]):
        avisos.append("Spec sem seção 'stack' (o painel mostrará a stack vazia)")
    usados_uc = {t.get("caso_de_uso") for t in spec["tasks"]}
    usados_req = {r for u in spec["casos_de_uso"] for r in (u.get("requisitos") or [])}
    avisos += [f"{r}: requisito sem caso de uso" for r in sorted(reqs - usados_req)]
    avisos += [f"{u}: caso de uso sem task" for u in sorted(ucs - usados_uc)]
    ligadas = {t for el in spec["uml"] for t in (el.get("tasks") or [])}
    avisos += [f"{el['id']}: elemento UML sem task" for el in spec["uml"] if not el.get("tasks")]
    avisos += [f"{t}: task fora de qualquer elemento da UML" for t in sorted(tasks - ligadas)] if spec["uml"] else []
    return erros, avisos


def ordem_topologica(spec):
    grafo = {t["id"]: set(t["depende_de"]) for t in spec["tasks"]}
    return list(TopologicalSorter(grafo).static_order())
