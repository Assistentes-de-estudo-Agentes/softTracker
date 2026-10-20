"""IA opcional. Só é chamada para critérios sem artefato esperado (ou com `usar_ia: true`).

Variáveis de ambiente: ANTHROPIC_API_KEY (obrigatória para ligar a IA) e HARNESS_MODEL (opcional).
Sem a chave, o harness funciona normalmente usando apenas os padrões do manifesto.
"""
import json
import os
import re
import urllib.request

MODELO_PADRAO = "claude-haiku-5-5"


def disponivel():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _chamar(prompt, max_tokens=600):
    corpo = json.dumps({"model": os.environ.get("HARNESS_MODEL", MODELO_PADRAO), "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=corpo, headers={
        "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dados = json.loads(r.read())
    texto = "".join(b.get("text", "") for b in dados.get("content", []))
    m = re.search(r"\{.*\}", texto, re.S)
    return json.loads(m.group(0)) if m else {}


def escolher(task, criterio, catalogo):
    """Passo 1 (barato): escolhe até 5 nós prováveis olhando só os NOMES. catalogo = [(id, tipo)]."""
    lista = "\n".join(f"{i}  [{t}]" for i, t in catalogo)
    out = _chamar(
        f"Task: {task['titulo']}\nCritério: {criterio['descricao']}\n\n"
        f"Nós do código (id [tipo]):\n{lista}\n\n"
        'Escolha até 5 ids que provavelmente implementam o critério. '
        'Responda só JSON: {"ids": ["..."]}. Use [] se nenhum servir.')
    return [i for i in out.get("ids", []) if isinstance(i, str)]


def julgar(task, criterio, trechos):
    """Passo 2: lê só os trechos escolhidos. trechos = [(id, codigo)]. Devolve (atendido, justificativa)."""
    codigo = "\n\n".join(f"### {i}\n{c}" for i, c in trechos)
    out = _chamar(
        f"Task: {task['titulo']}\nCritério: {criterio['descricao']}\n\nCódigo:\n{codigo}\n\n"
        'O código implementa o critério? Responda só JSON: {"atendido": true|false, "justificativa": "uma frase"}')
    return bool(out.get("atendido")), str(out.get("justificativa", ""))[:300]
