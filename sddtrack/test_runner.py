"""Execução controlada de testes do projeto-alvo e rastreabilidade dos resultados.

O executor só roda quando chamado explicitamente pelo comando `testar`. Comandos são
listas de argumentos (nunca shell=True), têm diretório de trabalho limitado ao projeto,
timeout e tamanho máximo para texto exibido/armazenado.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


class ErroConfiguracaoTestes(ValueError):
    pass


def configuracao(cfg):
    bruto = cfg.get("testes") or {}
    if not isinstance(bruto, dict):
        raise ErroConfiguracaoTestes("A seção 'testes' precisa ser um objeto.")
    return bruto


def testes_por_criterio(spec):
    """Retorna {test_id: [(task_id, criterion_id), ...]} com IDs estáveis."""
    relacoes = {}
    for task in spec.get("tasks", []):
        for criterio in task.get("criterios", []):
            ver = criterio.get("verificacao") or {}
            ids = ver.get("testes") or []
            if isinstance(ids, str):
                ids = [ids]
            for test_id in ids:
                relacoes.setdefault(str(test_id), []).append((task["id"], criterio["id"]))
    return {k: sorted(set(v)) for k, v in sorted(relacoes.items())}



def validar_config(cfg, spec=None):
    """Valida configuração de execução sem iniciar processos externos."""
    erros, avisos = [], []
    try:
        conf = configuracao(cfg)
    except ErroConfiguracaoTestes as exc:
        return [str(exc)], []
    ids_vinculados = testes_por_criterio(spec or {})
    if not conf:
        if ids_vinculados:
            avisos.append("A especificação vincula testes, mas não há seção 'testes' na configuração.")
        return erros, avisos
    if not conf.get("habilitado", False):
        if ids_vinculados:
            avisos.append("Há testes vinculados à especificação, mas testes.habilitado não está true.")
        return erros, avisos
    comando = conf.get("comando")
    if not isinstance(comando, list) or not comando or not all(isinstance(x, str) and x for x in comando):
        erros.append("'testes.comando' precisa ser uma lista de argumentos não vazios (não uma string shell).")
    if str(conf.get("formato", "junit")).lower() != "junit":
        erros.append("'testes.formato' atualmente precisa ser 'junit'.")
    try:
        _diretorio_execucao(os.path.realpath(cfg["projeto"]), conf.get("diretorio", "."))
    except (KeyError, ErroConfiguracaoTestes) as exc:
        erros.append(str(exc) or "'projeto' não está configurado.")
    try:
        timeout = int(conf.get("timeout_segundos", 60))
        if timeout < 1 or timeout > 1800:
            erros.append("'testes.timeout_segundos' precisa estar entre 1 e 1800.")
    except (TypeError, ValueError):
        erros.append("'testes.timeout_segundos' precisa ser um número inteiro.")
    arquivos = conf.get("arquivos") or []
    if isinstance(arquivos, str):
        arquivos = [arquivos]
    for rel in arquivos:
        path = _safe_file(cfg.get("projeto", ""), rel)
        if not path or not os.path.isfile(path):
            erros.append(f"Arquivo de teste configurado não existe ou está fora do projeto: {rel}")
    if isinstance(comando, list) and comando and not any("{pattern}" in x for x in comando):
        avisos.append("O comando não contém {pattern}; testar --impactados não poderá filtrar a execução por IDs.")
    if ids_vinculados and not arquivos:
        avisos.append("Configure 'testes.arquivos' para invalidar resultados quando o código dos testes mudar.")
    return erros, avisos

def _sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _safe_file(root, relative):
    if not isinstance(relative, str) or not relative.strip():
        return None
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, relative))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return path


def _hash_arquivos_teste(root, cfg_testes):
    arquivos = cfg_testes.get("arquivos") or []
    if isinstance(arquivos, str):
        arquivos = [arquivos]
    achados = {}
    for rel in sorted(set(str(x) for x in arquivos)):
        path = _safe_file(root, rel)
        if not path or not os.path.isfile(path):
            achados[rel] = "AUSENTE"
            continue
        try:
            with open(path, "rb") as f:
                achados[rel] = hashlib.sha256(f.read()).hexdigest()[:24]
        except OSError:
            achados[rel] = "ILEGIVEL"
    return achados


def fingerprints(spec, tasks_estado, grafo_codigo, raiz_projeto, cfg_testes):
    """Fingerprint por teste: spec + evidências/código relacionado + arquivos do teste.

    Se um critério ainda não tem símbolo candidato, cai para o fingerprint global de código,
    evitando manter um resultado aprovado quando a implementação ausente muda.
    """
    relacoes = testes_por_criterio(spec)
    criterios_spec = {}
    for task in spec.get("tasks", []):
        for criterio in task.get("criterios", []):
            ver = criterio.get("verificacao") or {}
            ids = ver.get("testes") or []
            if isinstance(ids, str):
                ids = [ids]
            for test_id in ids:
                criterios_spec.setdefault(str(test_id), []).append((task["id"], criterio["id"], criterio))
    nos = grafo_codigo.get("nos", {})
    arestas = grafo_codigo.get("arestas", [])
    saidas = {}
    files_test = _hash_arquivos_teste(raiz_projeto, cfg_testes)

    adj = {}
    for edge in arestas:
        a, b, tipo = edge.get("de"), edge.get("para"), edge.get("tipo")
        if a and b and tipo != "pertence_a":
            adj.setdefault(a, []).append(b)

    for test_id, links in relacoes.items():
        sementes = set()
        for tid, cid in links:
            rec = ((tasks_estado.get(tid) or {}).get("criterios") or {}).get(cid) or {}
            for ev in rec.get("evidencia") or []:
                if ev.get("no") in nos:
                    sementes.add(ev["no"])
        relacionados = set(sementes)
        pilha = list(sementes)
        while pilha:
            atual = pilha.pop()
            for nxt in adj.get(atual, []):
                if nxt in nos and nxt not in relacionados:
                    relacionados.add(nxt)
                    pilha.append(nxt)
        if relacionados:
            codigo = [(nid, nos[nid].get("hash")) for nid in sorted(relacionados)]
        else:
            # Evidência estrutural ausente: qualquer mudança no projeto pode afetar este teste.
            codigo = [(nid, no.get("hash")) for nid, no in sorted(nos.items())]
        payload = {
            # Só os critérios vinculados invalidam este teste; mudar um requisito sem
            # relação não deve forçar a reexecução de toda a suíte.
            "spec_criterios": [(tid, cid, criterio) for tid, cid, criterio in criterios_spec.get(test_id, [])],
            "teste": test_id,
            "links": links,
            "codigo": codigo,
            "arquivos_teste": files_test,
            "executor": {"comando": cfg_testes.get("comando"),
                         "formato": cfg_testes.get("formato", "junit"),
                         "diretorio": cfg_testes.get("diretorio", "."),
                         "timeout_segundos": cfg_testes.get("timeout_segundos", 60),
                         "env": cfg_testes.get("env") or {}},
        }
        saidas[test_id] = _sha_obj(payload)
    return saidas


def _texto_curto(value, max_chars=12000):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = str(value)
    return value if len(value) <= max_chars else value[-max_chars:]


def _extract_xml(texto):
    if not texto:
        return None
    inicio_candidatos = [i for i in (texto.find("<testsuites"), texto.find("<testsuite")) if i >= 0]
    if not inicio_candidatos:
        return None
    inicio = min(inicio_candidatos)
    for fechamento in ("</testsuites>", "</testsuite>"):
        fim = texto.rfind(fechamento)
        if fim >= inicio:
            return texto[inicio:fim + len(fechamento)]
    return None


def parsear_junit(texto):
    """Converte relatório JUnit XML para mapa de IDs de teste por nome."""
    xml = _extract_xml(texto)
    if not xml:
        return {}, "O comando não produziu um relatório JUnit XML reconhecível."
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        return {}, f"Relatório JUnit inválido: {exc}"
    resultados = {}
    for caso in raiz.iter():
        if caso.tag.split("}")[-1] != "testcase":
            continue
        nome = caso.attrib.get("name", "").strip()
        if not nome:
            continue
        estado = "aprovado"
        mensagem = ""
        for filho in list(caso):
            tipo = filho.tag.split("}")[-1]
            if tipo in ("failure", "error"):
                estado = "falhou"
                mensagem = (filho.attrib.get("message") or (filho.text or "")).strip()
                break
            if tipo in ("skipped", "ignored"):
                estado = "pulado"
                mensagem = (filho.attrib.get("message") or (filho.text or "")).strip()
        try:
            duracao = float(caso.attrib.get("time", 0) or 0)
        except (TypeError, ValueError):
            duracao = 0.0
        resultados[nome] = {"id": nome, "estado": estado, "mensagem": mensagem[:2000],
                            "duracao_segundos": round(duracao, 4)}
    return resultados, None


def _diretorio_execucao(root, relativo):
    relativo = relativo or "."
    path = _safe_file(root, relativo)
    if not path or not os.path.isdir(path):
        raise ErroConfiguracaoTestes("'testes.diretorio' precisa ser uma pasta existente dentro do projeto.")
    return path


def executar(cfg, test_ids=None):
    """Executa os testes configurados. `test_ids` limita apenas configurações com {pattern}."""
    conf = configuracao(cfg)
    if not conf.get("habilitado", False):
        raise ErroConfiguracaoTestes("Execução de testes não habilitada. Configure 'testes.habilitado': true.")
    errors, _warnings = validar_config(cfg, spec_carregado(cfg) if cfg.get("specs") else None)
    if errors:
        raise ErroConfiguracaoTestes("; ".join(errors))
    comando = conf.get("comando")
    if not isinstance(comando, list) or not comando or not all(isinstance(x, str) and x for x in comando):
        raise ErroConfiguracaoTestes("'testes.comando' precisa ser uma lista de argumentos, não uma string de shell.")
    formato = str(conf.get("formato", "junit")).lower()
    if formato != "junit":
        raise ErroConfiguracaoTestes("Formato de relatório ainda não suportado pelo executor: use 'junit'.")
    root = os.path.realpath(cfg["projeto"])
    cwd = _diretorio_execucao(root, conf.get("diretorio", "."))
    timeout = max(1, min(int(conf.get("timeout_segundos", 60)), 1800))
    max_chars = max(1000, min(int(conf.get("max_saida_caracteres", 12000)), 100000))

    tem_seletor = any("{pattern}" in x for x in comando)
    if test_ids and not tem_seletor:
        raise ErroConfiguracaoTestes("Execução seletiva solicitada, mas 'testes.comando' não contém o marcador {pattern}.")
    if test_ids:
        pattern = "^(?:" + "|".join(re.escape(x) for x in sorted(set(test_ids))) + ")$"
        cmd = [arg.replace("{pattern}", pattern) for arg in comando]
    else:
        cmd = [arg for arg in comando if "{pattern}" not in arg]
        cmd = [arg.replace("{pattern}", "") for arg in cmd]
    if not cmd:
        raise ErroConfiguracaoTestes("O comando de testes ficou vazio depois da substituição do seletor.")

    t0 = time.monotonic()
    inicio = time.strftime("%Y-%m-%dT%H:%M:%S")
    estado_execucao = "aprovado"
    saida, erro_saida, codigo = "", "", 0
    parse_erro = None
    try:
        proc = subprocess.run(cmd, cwd=cwd, shell=False, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              env={**os.environ, **{str(k): str(v) for k, v in (conf.get("env") or {}).items()}})
        codigo, saida, erro_saida = proc.returncode, proc.stdout or "", proc.stderr or ""
        if codigo != 0:
            estado_execucao = "falhou"
    except subprocess.TimeoutExpired as exc:
        codigo, estado_execucao = None, "timeout"
        saida, erro_saida = _texto_curto(exc.stdout, max_chars), _texto_curto(exc.stderr, max_chars)
    except OSError as exc:
        codigo, estado_execucao = None, "erro_execucao"
        erro_saida = f"{exc.__class__.__name__}: {exc}"

    junit, parse_erro = parsear_junit(saida)
    if not junit and estado_execucao == "aprovado":
        estado_execucao = "erro_relatorio"
    if test_ids is None:
        # Também exibe testes do relatório que ainda não foram vinculados a um critério.
        previstos = sorted(set(testes_por_criterio(spec_carregado(cfg))) | set(junit))
    else:
        previstos = sorted(set(test_ids))
    resultados = {}
    if estado_execucao in ("timeout", "erro_execucao", "erro_relatorio"):
        fallback_estado = estado_execucao
    elif estado_execucao == "falhou":
        fallback_estado = "erro_execucao"
    else:
        fallback_estado = "nao_encontrado"
    for test_id in previstos:
        item = junit.get(test_id)
        if item is None:
            # Aceita relatório que prefixe o nome do teste com um nome de suíte, mas não
            # associa por substring parcial para evitar misturar dois IDs parecidos.
            candidatos = [v for k, v in junit.items() if k.endswith("." + test_id) or k.endswith(" " + test_id)]
            item = candidatos[0] if len(candidatos) == 1 else None
        if item is None:
            item = {"id": test_id, "estado": fallback_estado, "mensagem": parse_erro or "Teste não encontrado no relatório.",
                    "duracao_segundos": 0.0}
        resultados[test_id] = item
    return {"executado_em": inicio, "duracao_segundos": round(time.monotonic() - t0, 3),
            "estado_execucao": estado_execucao, "codigo_saida": codigo, "comando": cmd,
            "diretorio_execucao": os.path.relpath(cwd, root).replace(os.sep, "/"),
            "formato": formato, "mensagem_relatorio": parse_erro,
            "stdout": _texto_curto(saida, max_chars), "stderr": _texto_curto(erro_saida, max_chars),
            "resultados": resultados}


def spec_carregado(cfg):
    # Import tardio evita ciclo entre spec e test_runner.
    from . import spec as spec_mod
    return spec_mod.carregar(cfg["specs"])


def mesclar_resultados(antigo, execucao, fingerprints_atuais):
    """Atualiza apenas testes executados; resultados de testes não executados são preservados."""
    antigo = antigo if isinstance(antigo, dict) else {}
    resultados = dict(antigo.get("resultados") or {})
    for test_id, item in (execucao.get("resultados") or {}).items():
        resultados[test_id] = {**item, "fingerprint": fingerprints_atuais.get(test_id),
                               "executado_em": execucao.get("executado_em"),
                               "duracao_segundos": item.get("duracao_segundos", 0.0)}
    return {"ultima_execucao": execucao.get("executado_em"),
            "estado_execucao": execucao.get("estado_execucao"),
            "duracao_segundos": execucao.get("duracao_segundos", 0),
            "comando": execucao.get("comando", []),
            "resultados": resultados,
            "resumo_ultima_execucao": {
                "total": len(execucao.get("resultados") or {}),
                "aprovados": sum(x.get("estado") == "aprovado" for x in (execucao.get("resultados") or {}).values()),
                "falhos": sum(x.get("estado") in {"falhou", "erro_execucao", "timeout", "erro_relatorio"} for x in (execucao.get("resultados") or {}).values()),
                "pulados": sum(x.get("estado") == "pulado" for x in (execucao.get("resultados") or {}).values())}}


def estado_teste(test_id, fingerprint_atual, armazenamento):
    registrado = ((armazenamento or {}).get("resultados") or {}).get(test_id)
    if not registrado:
        return {"id": test_id, "estado": "nao_executada", "mensagem": "Nenhum resultado registrado."}
    if not fingerprint_atual or registrado.get("fingerprint") != fingerprint_atual:
        return {"id": test_id, "estado": "desatualizada", "mensagem": "O código, a especificação ou o teste mudou após a execução."}
    return {"id": test_id, "estado": registrado.get("estado", "nao_executada"),
            "mensagem": registrado.get("mensagem", ""),
            "executado_em": registrado.get("executado_em"),
            "duracao_segundos": registrado.get("duracao_segundos", 0)}


def agregar_estado(itens):
    estados = [x.get("estado") for x in itens]
    if not estados:
        return "nao_exigida"
    if any(x in {"falhou", "erro_execucao", "timeout", "erro_relatorio"} for x in estados):
        return "falhou"
    if any(x == "desatualizada" for x in estados):
        return "desatualizada"
    if all(x == "aprovado" for x in estados):
        return "aprovada"
    if any(x == "pulado" for x in estados):
        return "incompleta"
    return "nao_executada"


def aplicar_validacao(spec, tasks_estado, grafo_codigo, armazenamento, cfg):
    """Anexa estado comportamental aos critérios/tasks sem alterar o status estático."""
    conf = configuracao(cfg)
    relacoes = testes_por_criterio(spec)
    current_fps = fingerprints(spec, tasks_estado, grafo_codigo, cfg["projeto"], conf)
    todos_estados = {tid: estado_teste(tid, current_fps.get(tid), armazenamento) for tid in relacoes}

    for task in spec.get("tasks", []):
        task_state = tasks_estado.get(task["id"], {})
        critérios_com_teste = []
        for criterio in task.get("criterios", []):
            rec = (task_state.get("criterios") or {}).get(criterio["id"])
            if rec is None:
                continue
            ver = criterio.get("verificacao") or {}
            ids = ver.get("testes") or []
            if isinstance(ids, str):
                ids = [ids]
            itens = [todos_estados.get(str(tid), {"id": str(tid), "estado": "nao_executada",
                                                   "mensagem": "Teste ainda não foi registrado."}) for tid in ids]
            rec["validacao_testes"] = {"obrigatoria": bool(ver.get("obrigatoria", True)) if ids else False,
                                       "estado": agregar_estado(itens), "testes": itens}
            if ids and ver.get("obrigatoria", True):
                critérios_com_teste.extend(itens)
        task_state["status_validacao"] = agregar_estado({x["id"]: x for x in critérios_com_teste}.values()) if critérios_com_teste else "nao_exigida"

    # Resumo único para CLI e painel: considera todos os IDs referenciados na especificação.
    estados = list(todos_estados.values())
    summary = {
        "habilitado": bool(conf.get("habilitado")),
        "total": len(relacoes),
        "aprovados": sum(x["estado"] == "aprovado" for x in estados),
        "falhos": sum(x["estado"] in {"falhou", "erro_execucao", "timeout", "erro_relatorio"} for x in estados),
        "desatualizados": sum(x["estado"] == "desatualizada" for x in estados),
        "nao_executados": sum(x["estado"] in {"nao_executada", "pulado", "incompleta"} for x in estados),
        "ultima_execucao": (armazenamento or {}).get("ultima_execucao"),
        "estado_ultima_execucao": (armazenamento or {}).get("estado_execucao"),
        "testes": todos_estados,
        "por_status_task": {s: sum((t.get("status_validacao") == s) for t in tasks_estado.values())
                             for s in ("aprovada", "falhou", "desatualizada", "nao_executada", "nao_exigida", "incompleta")},
    }
    return summary, current_fps
