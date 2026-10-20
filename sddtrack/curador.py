"""Curadoria: leva você até a task escolhida e avisa o que falta antes dela."""
SIMB = {"feita": "■", "parcial": "◧", "nao_feita": "□", "revalidar": "◌"}


def pendencias(estado, task_id):
    """Dependências (diretas e indiretas) ainda não feitas, da mais profunda para a mais próxima."""
    tasks, vistos, ordem = estado["tasks"], set(), []

    def visitar(i):
        for d in tasks[i]["depende_de"]:
            if d not in vistos:
                vistos.add(d)
                visitar(d)
                if tasks[d]["status"] != "feita":
                    ordem.append(d)
    visitar(task_id)
    return ordem


def proximas(estado):
    """Tasks não feitas cujas dependências já estão todas feitas (podem começar agora)."""
    t = estado["tasks"]
    return [i for i, x in t.items() if x["status"] != "feita" and all(t[d]["status"] == "feita" for d in x["depende_de"])]


def detalhe(estado, task_id):
    t = estado["tasks"][task_id]
    linhas = [f"{SIMB[t['status']]} {task_id} — {t['titulo']}  [{t['status']}]"]
    for cid, c in t["criterios"].items():
        marca = "✔" if c["atendido"] else "✘"
        extra = " (revalidar)" if c.get("revalidar") else ""
        linhas.append(f"    {marca} {cid}: {t['descricoes'].get(cid, '')}{extra}")
        for e in c["evidencia"][:3]:
            linhas.append(f"        ↳ {e['no']}")
    return "\n".join(linhas)


def ir_para(task_id, sincronizar, interativo=True, entrada=input, saida=print):
    """`sincronizar` é uma função sem argumentos que reanalisa o projeto e devolve o estado novo."""
    estado = sincronizar()
    if task_id not in estado["tasks"]:
        saida(f"Task '{task_id}' não existe na especificação.")
        return estado
    while True:
        pend = pendencias(estado, task_id)
        if not pend:
            saida(detalhe(estado, task_id))
            saida("\nSem pendências anteriores. Pode seguir." if estado["tasks"][task_id]["status"] != "feita"
                  else "\nEssa task já está feita.")
            return estado
        saida(f"\nAntes de {task_id}, há pendências:")
        for p in pend:
            t = estado["tasks"][p]
            ok = sum(c["atendido"] for c in t["criterios"].values())
            saida(f"  {SIMB[t['status']]} {p} — {t['titulo']}  [{t['status']}, {ok}/{len(t['criterios'])} critérios]")
        if not interativo:
            return estado
        saida("\nO que prefere?\n  1) Fazer a anterior primeiro\n  2) Atualizar a análise (alguém pode já ter feito)\n"
              "  3) Seguir mesmo assim")
        try:
            r = entrada("> ").strip()
        except (EOFError, KeyboardInterrupt):
            saida("\nSaindo.")
            return estado
        if r == "1":
            saida("\nComece por:\n" + detalhe(estado, pend[0]))
            return estado
        if r == "2":
            estado = sincronizar()
            saida("Análise atualizada.")
            continue
        if r == "3":
            saida("\nSeguindo, com as pendências registradas:\n" + detalhe(estado, task_id))
            return estado
        saida("Opção inválida.")
