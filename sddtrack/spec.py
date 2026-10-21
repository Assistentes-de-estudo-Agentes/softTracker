"""Carrega, normaliza e valida especificações canônicas e legadas (YAML/JSON)."""
import hashlib
import json
import re
from graphlib import CycleError, TopologicalSorter

TIPOS_ARTEFATO = {"rota", "funcao", "classe", "arquivo", "simbolo", "conteudo"}
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
        dados = yaml.safe_load(texto) or {}
    else:
        dados = json.loads(texto)
    if not isinstance(dados, dict):
        raise ValueError(f"A raiz da especificação precisa ser um objeto: {caminho}")
    return dados, texto


def _normalizar_stack(bruto):
    """Aceita lista de camadas, mapa camada->itens ou mapa de propriedades simples."""
    if not bruto:
        return []
    if isinstance(bruto, dict):
        convertido = []
        for camada, valor in bruto.items():
            itens = valor if isinstance(valor, (list, tuple)) else [valor]
            convertido.append({"camada": str(camada).replace("_", " ").title(), "itens": itens})
        bruto = convertido
    if not isinstance(bruto, list):
        return []
    grupos = []
    for g in bruto:
        if isinstance(g, str):
            g = {"camada": "Stack", "itens": [g]}
        if not isinstance(g, dict):
            continue
        valores = g.get("itens") or []
        if isinstance(valores, (str, dict)):
            valores = [valores]
        itens = []
        for item in valores:
            if isinstance(item, str):
                item = {"nome": item}
            if isinstance(item, dict) and item.get("nome"):
                itens.append({"nome": str(item["nome"]), "uso": str(item.get("uso", ""))})
        if itens:
            grupos.append({"camada": str(g.get("camada", "Stack")), "itens": itens})
    return grupos


def _normalizar_requisito(item, tipo="funcional"):
    if not isinstance(item, dict):
        return None
    r = dict(item)
    if not r.get("id"):
        return None
    r.setdefault("titulo", r.get("descricao", r["id"]))
    r.setdefault("tipo", tipo)
    return r


def _normalizar_caso_uso(item):
    if not isinstance(item, dict):
        return item
    u = dict(item)
    if "titulo" not in u:
        u["titulo"] = u.get("nome", u.get("descricao", u.get("id", "Caso de uso")))
    if "requisitos" not in u:
        requisito = u.get("requisito")
        u["requisitos"] = [requisito] if isinstance(requisito, str) and requisito else []
    elif isinstance(u["requisitos"], str):
        u["requisitos"] = [u["requisitos"]]
    return u


def _rota_artefato(endpoint):
    """Transforma uma rota HTTP declarada em um artefato de rota normalizado."""
    endpoint = str(endpoint).strip()
    m = re.match(r"(?i)^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(.+)$", endpoint)
    if not m:
        return None
    caminho = re.sub(r"(:\w+|\{[^}]+\}|<[^>]+>)", "*", m.group(2).strip())
    return {"tipo": "rota", "padrao": f"{m.group(1).upper()} {caminho}"}


def _converter_tarefas_legadas(tarefas, casos):
    """Converte tarefas_desenvolvimento para tasks com critérios rastreáveis."""
    por_uc = {u.get("id"): u for u in casos if isinstance(u, dict) and u.get("id")}
    saida = []
    for original in tarefas or []:
        if not isinstance(original, dict) or not original.get("id"):
            continue
        t = dict(original)
        t["titulo"] = t.get("titulo", t.get("descricao", t["id"]))
        associados = t.get("casos_de_uso") or t.get("relacionado_a") or []
        if isinstance(associados, str):
            associados = [associados]
        t["casos_de_uso"] = list(dict.fromkeys(x for x in associados if x))
        if len(t["casos_de_uso"]) == 1:
            t["caso_de_uso"] = t["casos_de_uso"][0]
        elif not t.get("caso_de_uso"):
            t["caso_de_uso"] = None
        t["depende_de"] = t.get("depende_de") or []

        criterios = list(t.get("criterios") or [])
        if not criterios:
            criterios = []
            contador = 1
            for uc_id in t["casos_de_uso"]:
                uc = por_uc.get(uc_id, {})
                endpoint = uc.get("endpoint") or uc.get("endpoint_planejado")
                artefato = _rota_artefato(endpoint) if endpoint else None
                if artefato:
                    criterios.append({
                        "id": f"C{contador}",
                        "descricao": f"Existe o endpoint {endpoint}",
                        "artefato": artefato,
                        "tipo_evidencia": "estrutural",
                    })
                    contador += 1
                for descricao in uc.get("criterios_aceitacao") or []:
                    criterios.append({
                        "id": f"C{contador}",
                        "descricao": str(descricao),
                        "usar_ia": True,
                    })
                    contador += 1
            # Tasks legadas sem caso de uso continuam rastreáveis sem presumir
            # linguagem, framework, nome de classe ou ferramenta de build.
            if not criterios:
                descricao = str(t.get("descricao", t["titulo"]))
                criterios.append({"id": "C1", "descricao": descricao, "usar_ia": True})
        t["criterios"] = criterios
        # Campos específicos da nomenclatura antiga não precisam contaminar o motor.
        t.pop("relacionado_a", None)
        saida.append(t)
    return saida


def carregar(caminhos):
    """Lê uma ou mais especificações e as converte para o modelo interno único."""
    spec = {"requisitos": [], "casos_de_uso": [], "uml": [], "tasks": [], "ignorar": [], "stack": []}
    requisitos_funcionais, requisitos_nao_funcionais, tarefas_legadas = [], [], []
    hash_spec = hashlib.sha256()
    projetos = []
    for caminho in caminhos:
        dados, texto = _ler(caminho)
        hash_spec.update(texto.encode("utf-8"))
        # Mantém o formato nativo e também importa os nomes usados pela especificação legada.
        spec["requisitos"].extend(dados.get("requisitos") or [])
        spec["casos_de_uso"].extend(dados.get("casos_de_uso") or [])
        spec["uml"].extend(dados.get("uml") or [])
        spec["tasks"].extend(dados.get("tasks") or [])
        spec["ignorar"].extend(dados.get("ignorar") or [])
        stack_bruta = dados.get("stack")
        if not stack_bruta and isinstance(dados.get("projeto"), dict):
            stack_bruta = dados["projeto"].get("stack")
        spec["stack"].extend(_normalizar_stack(stack_bruta))
        requisitos_funcionais.extend(dados.get("requisitos_funcionais") or [])
        requisitos_nao_funcionais.extend(dados.get("requisitos_nao_funcionais") or [])
        tarefas_legadas.extend(dados.get("tarefas_desenvolvimento") or [])
        if dados.get("projeto"):
            projetos.append(dados["projeto"])

    # Só importa campos legados quando o mesmo ID ainda não foi definido no modelo nativo.
    ids_requisitos = {r.get("id") for r in spec["requisitos"] if isinstance(r, dict)}
    for r in requisitos_funcionais:
        normalizado = _normalizar_requisito(r, "funcional")
        if normalizado and normalizado["id"] not in ids_requisitos:
            spec["requisitos"].append(normalizado)
            ids_requisitos.add(normalizado["id"])
    for r in requisitos_nao_funcionais:
        normalizado = _normalizar_requisito(r, "nao_funcional")
        if normalizado and normalizado["id"] not in ids_requisitos:
            spec["requisitos"].append(normalizado)
            ids_requisitos.add(normalizado["id"])

    spec["casos_de_uso"] = [_normalizar_caso_uso(u) for u in spec["casos_de_uso"]]
    # Não silencie uma spec que usa tarefas_desenvolvimento em vez de tasks.
    if not spec["tasks"] and tarefas_legadas:
        spec["tasks"] = _converter_tarefas_legadas(tarefas_legadas, spec["casos_de_uso"])
    # Padroniza também tarefas no formato nativo.
    for t in spec["tasks"]:
        t["depende_de"] = t.get("depende_de") or []
        relacionados = t.get("casos_de_uso") or t.get("relacionado_a") or []
        if isinstance(relacionados, str):
            relacionados = [relacionados]
        if not relacionados and t.get("caso_de_uso"):
            relacionados = [t["caso_de_uso"]]
        t["casos_de_uso"] = list(dict.fromkeys(x for x in relacionados if x))
        if len(t["casos_de_uso"]) == 1:
            t["caso_de_uso"] = t["casos_de_uso"][0]
        elif not t.get("caso_de_uso"):
            t["caso_de_uso"] = None
        criterios = []
        for i, criterio in enumerate(t.get("criterios") or [], 1):
            if isinstance(criterio, str):
                criterio = {"descricao": criterio}
            criterio.setdefault("id", f"C{i}")
            criterio.setdefault("descricao", "")
            criterios.append(criterio)
        t["criterios"] = criterios
    if projetos:
        p = projetos[-1]
        spec["projeto"] = p.get("nome", "Projeto") if isinstance(p, dict) else str(p)
        if isinstance(p, dict):
            spec["projeto_meta"] = p
    spec["hash"] = hash_spec.hexdigest()
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
        for r in (u.get("requisitos") or []):
            if r not in reqs:
                erros.append(f"{u.get('id')}: requisito inexistente '{r}'")
    for el in spec["uml"]:
        for t in el.get("tasks") or []:
            if t not in tasks:
                erros.append(f"{el.get('id')}: task inexistente '{t}'")
    grafo = {}
    for t in spec["tasks"]:
        tid = t.get("id")
        relacionados = t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else [])
        for uc in relacionados:
            if uc not in ucs:
                erros.append(f"{tid}: caso de uso inexistente '{uc}'")
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
            verificacao = c.get("verificacao")
            if verificacao is not None:
                if not isinstance(verificacao, dict):
                    erros.append(f"{tid}/{c['id']}: 'verificacao' precisa ser um objeto")
                else:
                    ids_teste = verificacao.get("testes") or []
                    if isinstance(ids_teste, str):
                        ids_teste = [ids_teste]
                    if not isinstance(ids_teste, list) or any(not isinstance(x, str) or not x.strip() for x in ids_teste):
                        erros.append(f"{tid}/{c['id']}: verificacao.testes precisa ser uma lista de IDs não vazios")
                    elif len(ids_teste) != len(set(ids_teste)):
                        erros.append(f"{tid}/{c['id']}: verificacao.testes contém IDs duplicados")
                    if "obrigatoria" in verificacao and not isinstance(verificacao.get("obrigatoria"), bool):
                        erros.append(f"{tid}/{c['id']}: verificacao.obrigatoria precisa ser true/false")
            art = c.get("artefato")
            if art:
                if art.get("tipo") not in TIPOS_ARTEFATO:
                    erros.append(f"{tid}/{c['id']}: tipo de artefato inválido '{art.get('tipo')}'")
                if not art.get("padrao"):
                    erros.append(f"{tid}/{c['id']}: artefato sem padrão")
                escopo = art.get("escopo")
                if escopo and art.get("tipo") != "conteudo":
                    erros.append(f"{tid}/{c['id']}: escopo só é permitido em artefatos do tipo 'conteudo'")
                elif escopo:
                    if isinstance(escopo, str):
                        escopo_tipo, escopo_padrao = "funcao", escopo
                    elif isinstance(escopo, dict):
                        escopo_tipo = escopo.get("tipo", "funcao")
                        escopo_padrao = escopo.get("padrao")
                    else:
                        escopo_tipo, escopo_padrao = None, None
                    if escopo_tipo not in {"funcao", "classe", "rota", "simbolo"}:
                        erros.append(f"{tid}/{c['id']}: tipo de escopo inválido '{escopo_tipo}'")
                    if not (escopo_padrao or (isinstance(escopo_padrao, (list, tuple)) and escopo_padrao)):
                        erros.append(f"{tid}/{c['id']}: escopo sem padrão de símbolo")
            else:
                avisos.append(f"{tid}/{c['id']}: sem artefato determinístico (requer análise semântica) ")
            if any(p in c.get("descricao", "").lower() for p in PALAVRAS_VAGAS) and not art:
                avisos.append(f"{tid}/{c['id']}: critério possivelmente vago")
    try:
        list(TopologicalSorter(grafo).static_order())
    except CycleError as e:
        erros.append(f"Ciclo nas dependências: {' -> '.join(map(str, e.args[1]))}")

    if not spec["tasks"]:
        erros.append("Nenhuma task reconhecida. Use 'tasks' ou 'tarefas_desenvolvimento' na especificação.")
    if not spec["requisitos"]:
        avisos.append("Spec sem requisitos reconhecidos.")
    if not spec["casos_de_uso"]:
        avisos.append("Spec sem casos de uso reconhecidos.")
    if not any(g["itens"] for g in spec["stack"]):
        avisos.append("Spec sem seção 'stack' reconhecível (o painel mostrará a stack vazia).")
    usados_uc = {uc for t in spec["tasks"] for uc in (t.get("casos_de_uso") or ([t["caso_de_uso"]] if t.get("caso_de_uso") else []))}
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
