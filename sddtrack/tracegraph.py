"""Grafo de rastreabilidade entre requisitos, casos de uso, tarefas, critérios e código.

O grafo é um índice de relações persistente no status. Ele permite explicar evidências e
calcular o conjunto afetado por uma alteração sem comparar todos os pares possíveis.
"""
from collections import defaultdict, deque


def _id(tipo, valor):
    return f"{tipo}:{valor}"


def construir(spec, tasks_estado, grafo_codigo, pendentes=None, estados_testes=None):
    nos = []
    arestas = []
    ids = set()
    estados_testes = estados_testes or {}
    tarefas_spec = {t.get("id"): t for t in spec.get("tasks", [])}

    def no(identificador, tipo, titulo, **extras):
        if identificador in ids:
            return
        ids.add(identificador)
        nos.append({"id": identificador, "tipo": tipo, "titulo": str(titulo or identificador), **extras})

    def aresta(origem, destino, tipo):
        if origem and destino:
            arestas.append({"de": origem, "para": destino, "tipo": tipo})

    # Especificação: requisito -> caso de uso -> tarefa -> critério.
    for requisito in spec.get("requisitos", []):
        rid = _id("requisito", requisito["id"])
        relacionadas = [u for u in spec.get("casos_de_uso", []) if requisito["id"] in (u.get("requisitos") or [])]
        estados = [u.get("status") for u in relacionadas if u.get("status")]
        no(rid, "requisito", requisito.get("titulo", requisito.get("descricao", requisito["id"])),
           tipo_requisito=requisito.get("tipo", "funcional"))
        for uc in relacionadas:
            ucid = _id("caso_de_uso", uc["id"])
            aresta(rid, ucid, "realizado_em")

    for uc in spec.get("casos_de_uso", []):
        ucid = _id("caso_de_uso", uc["id"])
        no(ucid, "caso_de_uso", uc.get("titulo", uc.get("nome", uc["id"])))

    tasks_raw = {t["id"]: t for t in spec.get("tasks", [])}
    for tid, estado in tasks_estado.items():
        raw = tasks_raw.get(tid, {})
        tid_node = _id("task", tid)
        no(tid_node, "task", estado.get("titulo", tid), status=estado.get("status", "nao_feita"))
        relacionados = raw.get("casos_de_uso") or ([raw["caso_de_uso"]] if raw.get("caso_de_uso") else [])
        for uc in relacionados:
            aresta(_id("caso_de_uso", uc), tid_node, "implementado_por")
        for dependencia in raw.get("depende_de") or []:
            aresta(_id("task", dependencia), tid_node, "prerequisito_de")
        for cid, criterio in (estado.get("criterios") or {}).items():
            criterio_id = _id("criterio", f"{tid}/{cid}")
            no(criterio_id, "criterio", criterio.get("descricao", cid),
               status="atendido" if criterio.get("atendido") else ("revalidar" if criterio.get("revalidar") else "pendente"),
               nivel_evidencia=criterio.get("nivel_evidencia", "nenhuma"))
            aresta(tid_node, criterio_id, "possui_criterio")
            for evidencia in criterio.get("evidencia", []):
                codigo_id = evidencia.get("no")
                if not codigo_id:
                    continue
                tipo_codigo = (grafo_codigo.get("nos", {}).get(codigo_id) or {}).get("tipo")
                destino_codigo = _id("arquivo", codigo_id) if tipo_codigo == "arquivo" else _id("codigo", codigo_id)
                aresta(criterio_id, destino_codigo, "evidenciado_por")
            criterio_spec = next((c for c in tarefas_spec.get(tid, {}).get("criterios", [])
                                  if c.get("id") == cid), {})
            verificacao = criterio_spec.get("verificacao") or {}
            ids_testes = verificacao.get("testes") or []
            if isinstance(ids_testes, str):
                ids_testes = [ids_testes]
            for test_id in ids_testes:
                test_node = _id("teste", str(test_id))
                estado_teste = estados_testes.get(str(test_id), {}).get("estado", "nao_executada")
                no(test_node, "teste", str(test_id), status=estado_teste)
                aresta(criterio_id, test_node, "verificado_por")

    # Arquivos e símbolos do índice de código.
    nos_codigo = grafo_codigo.get("nos", {})
    for nid, item in nos_codigo.items():
        if item.get("tipo") == "arquivo":
            no(_id("arquivo", nid), "arquivo", nid, hash=item.get("hash"))
        else:
            no(_id("codigo", nid), "codigo", item.get("nome", nid), subtipo=item.get("tipo"),
               arquivo=item.get("arquivo"), hash=item.get("hash"), linha_inicio=item.get("ini"))
            aresta(_id("codigo", nid), _id("arquivo", item.get("arquivo")), "pertence_a")
    for e in grafo_codigo.get("arestas", []):
        aresta(_id("codigo", e.get("de")), _id("codigo", e.get("para")), e.get("tipo", "relacionado_a"))

    # Candidatos de uma análise pendente também são arestas explícitas: ajudam a explicar
    # por que um critério foi sugerido para revisão e permitem calcular impacto depois.
    for p in pendentes or []:
        criterio_id = _id("criterio", p.get("chave", ""))
        for candidato in p.get("candidatos", []):
            aresta(criterio_id, _id("codigo", candidato), "candidato_a")

    # Deduplicação determinística para manter JSON compacto e estável entre sincronizações.
    unique = {(e["de"], e["para"], e["tipo"]): e for e in arestas}
    arestas = [unique[k] for k in sorted(unique)]
    return {"nos": sorted(nos, key=lambda n: n["id"]), "arestas": arestas,
            "estatisticas": {"nos": len(nos), "arestas": len(arestas),
                             "requisitos": sum(n["tipo"] == "requisito" for n in nos),
                             "tarefas": sum(n["tipo"] == "task" for n in nos),
                             "criterios": sum(n["tipo"] == "criterio" for n in nos),
                             "testes": sum(n["tipo"] == "teste" for n in nos),
                             "simbolos_codigo": sum(n["tipo"] == "codigo" for n in nos)}}


def impacto(grafo_novo, grafo_antigo, codigos_alterados):
    """Retorna os critérios/tasks ancestrais alcançáveis a partir de código alterado/removido."""
    if not codigos_alterados:
        return {"codigos_alterados": [], "criterios_afetados": [], "tasks_afetadas": []}
    arestas = []
    for g in (grafo_antigo or {}, grafo_novo or {}):
        arestas.extend(g.get("arestas", []))
    # relações duplicadas não mudam a busca e são removidas para reduzir trabalho.
    unique = {(e.get("de"), e.get("para"), e.get("tipo")) for e in arestas}
    entrada = defaultdict(list)
    for origem, destino, tipo in unique:
        entrada[destino].append((origem, tipo))

    sementes = set()
    for codigo in codigos_alterados:
        sementes.add(_id("codigo", codigo))
        sementes.add(_id("arquivo", codigo))
    visitados = set(sementes)
    fila = deque(sementes)
    while fila:
        atual = fila.popleft()
        for pai, tipo_aresta in entrada.get(atual, []):
            # Uma mudança no hash bruto de um arquivo não deve automaticamente marcar
            # todos os símbolos dele como alterados. Alterações semânticas nos símbolos
            # têm sementes próprias; ainda seguimos evidências diretamente ligadas ao arquivo.
            if atual.startswith("arquivo:") and tipo_aresta == "pertence_a":
                continue
            if pai not in visitados:
                visitados.add(pai)
                fila.append(pai)

    criterios = sorted(n.split(":", 1)[1] for n in visitados if n.startswith("criterio:"))
    tasks = sorted(n.split(":", 1)[1] for n in visitados if n.startswith("task:"))
    criterios_ids = {_id("criterio", chave) for chave in criterios}
    testes_afetados = sorted({
        destino.split(":", 1)[1] for origem, destino, tipo in unique
        if origem in criterios_ids and tipo == "verificado_por" and destino.startswith("teste:")
    })
    return {"codigos_alterados": sorted(set(codigos_alterados)),
            "criterios_afetados": criterios, "tasks_afetadas": tasks,
            "testes_afetados": testes_afetados}
