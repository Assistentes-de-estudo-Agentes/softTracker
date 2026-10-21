#!/usr/bin/env python3
"""Harness de acompanhamento: vincula a especificação ao código e mostra o que está feito e o que falta."""
import argparse
import json
import os
import sys
import time

from sddtrack import curador, engine, estado as est, indexer, spec as spec_mod
from sddtrack.curador import SIMB


def carregar_cfg(caminho):
    if not os.path.exists(caminho):
        raise SystemExit("Config não encontrada. Rode primeiro: harness.py init --projeto PASTA --spec ARQ [ARQ...]")
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(caminho))
    cfg["estado"] = os.path.join(base, cfg.get("estado", "estado"))
    return cfg


def sync(cfg, args, silencioso=False):
    with est.trava(cfg):
        try:
            novo = engine.sincronizar(cfg, usar_ia=getattr(args, "ia_api", False),
                                      max_ia=getattr(args, "max_ia", 20), simular=getattr(args, "simular", False))
        except engine.ErroSpec as e:
            print("Especificação inválida:")
            for m in e.args[0]:
                print("  ✘", m)
            raise SystemExit(1)
    if not silencioso:
        for m in novo["mudancas"]:
            print("•", m)
        if not novo["mudancas"]:
            print("Nada mudou.")
    return novo


def est_codigo(cfg):
    with open(os.path.join(cfg["estado"], est.CODIGO), encoding="utf-8") as f:
        return json.load(f)["nos"]


def engine_pendentes(cfg):
    return json.load(open(os.path.join(cfg["estado"], est.STATUS), encoding="utf-8")).get("pendentes_ia", [])


def mostrar_status(e, detalhado=True):
    r = e["resumo"]
    n = r["tasks_total"]
    largura = 30
    cheio = int(round(r["progresso_tasks"] * largura))
    print(f"\nProjeto: {e['projeto'] or '-'}   último sync: {e['ultimo_sync']}")
    print(f"Progresso: [{'█' * cheio}{'░' * (largura - cheio)}] {r['progresso_tasks']:.0%}  "
          f"({r['tasks_feitas']}/{n} tasks · {r['criterios_atendidos']}/{r['criterios_total']} critérios)")
    print("Blocos:   ", " ".join(SIMB[t["status"]] for t in e["tasks"].values()))
    print("Legenda:   ■ feita  ◧ parcial  □ não feita  ◌ revalidar")
    if detalhado:
        print()
        for i in e["tasks"]:
            print(curador.detalhe(e, i))
    if e["codigo_sem_task"]:
        print(f"\nCódigo sem task vinculada: {', '.join(e['codigo_sem_task'][:8])}"
              + (" …" if len(e["codigo_sem_task"]) > 8 else ""))
    if e.get("pendentes_ia"):
        print(f"\n{len(e['pendentes_ia'])} critério(s) aguardando julgamento (rode `pendentes`).")
    for a in e["avisos"]:
        print("⚠", a)


def modo_padrao(args, ap):
    base = os.path.dirname(os.path.abspath(args.config))
    if not os.path.exists(args.config):
        pasta_spec, pasta_proj = os.path.join(base, "spec"), os.path.join(base, "projeto")
        specs = sorted(os.path.join(pasta_spec, f) for f in (os.listdir(pasta_spec) if os.path.isdir(pasta_spec) else [])
                       if f.lower().endswith((".yaml", ".yml", ".json")))
        if not (specs and os.path.isdir(pasta_proj)):
            print("Primeira vez? Coloque a especificação em spec/ (YAML ou JSON) e o código em projeto/,\n"
                  "ou informe os caminhos:\n\n"
                  "  python harness.py init --projeto PASTA --spec ARQUIVO [ARQUIVO...]\n\n"
                  "Depois rode `python harness.py` de novo para abrir o painel.\n")
            ap.print_help()
            raise SystemExit(1)
        cfg = {"projeto": pasta_proj, "specs": specs, "estado": "estado"}
        with open(args.config, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"Configuração criada: projeto = {pasta_proj}; spec = {', '.join(os.path.basename(x) for x in specs)}")
    cfg = carregar_cfg(args.config)
    erros, _ = spec_mod.validar(spec_mod.carregar(cfg["specs"]))
    if erros:
        print("A especificação tem erros (corrija antes de abrir o painel):")
        for m in erros:
            print("  ✘", m)
        raise SystemExit(1)
    from sddtrack import painel
    painel.servir(cfg, args.porta, abrir=not args.sem_abrir)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="harness.json")
    ap.add_argument("--porta", type=int, default=8765, help="porta do painel (sem subcomando)")
    ap.add_argument("--sem-abrir", action="store_true", help="não abre o navegador (sem subcomando)")
    sub = ap.add_subparsers(dest="cmd", metavar="comando")
    p = sub.add_parser("init", help="registra projeto e arquivos de especificação")
    p.add_argument("--projeto", required=True)
    p.add_argument("--spec", nargs="+", required=True)
    for nome in ("sync", "status", "watch"):
        p = sub.add_parser(nome)
        p.add_argument("--ia-api", action="store_true", help="(opcional) julgar via API Anthropic; no Antigravity o agente julga")
        p.add_argument("--max-ia", type=int, default=20, help="limite de consultas à IA por execução")
        if nome == "sync":
            p.add_argument("--simular", action="store_true", help="mostra o que mudaria sem gravar")
        if nome == "status":
            p.add_argument("--resumo", action="store_true")
            p.add_argument("--json", action="store_true")
        if nome == "watch":
            p.add_argument("--intervalo", type=float, default=3.0)
    p = sub.add_parser("go", help="escolhe uma task; o curador avisa pendências")
    p.add_argument("task")
    p.add_argument("--sem-perguntar", action="store_true")
    sub.add_parser("proxima", help="tasks que já podem ser começadas")
    sub.add_parser("validar", help="valida só o manifesto")
    p = sub.add_parser("painel", help="abre o painel local no navegador")
    p.add_argument("--porta", type=int, default=8765)
    p.add_argument("--sem-abrir", action="store_true")
    p = sub.add_parser("pendentes", help="critérios que precisam de julgamento (para o agente)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("trecho", help="imprime o código de um nó")
    p.add_argument("no")
    p = sub.add_parser("link", help="registra que o critério é atendido por estes nós")
    p.add_argument("alvo", help="TASK-001/C1")
    p.add_argument("nos", nargs="+", help="ids de nó existentes (veja `pendentes` ou estado/codigo.json)")
    p = sub.add_parser("nao-feito", help="registra que os candidatos atuais NÃO atendem o critério")
    p.add_argument("alvo")
    p = sub.add_parser("unlink")
    p.add_argument("alvo")
    args = ap.parse_args()

    if args.cmd is None:  # sem subcomando: configura na primeira vez e abre o painel
        modo_padrao(args, ap)
        return
    if args.cmd == "init":
        cfg = {"projeto": os.path.abspath(args.projeto), "specs": [os.path.abspath(s) for s in args.spec],
               "estado": "estado"}
        with open(args.config, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("Config gravada em", args.config)
        return
    cfg = carregar_cfg(args.config)

    if args.cmd == "validar":
        erros, avisos = spec_mod.validar(spec_mod.carregar(cfg["specs"]))
        for m in erros:
            print("✘", m)
        for m in avisos:
            print("⚠", m)
        print("Manifesto válido." if not erros else f"{len(erros)} erro(s).")
        sys.exit(1 if erros else 0)
    if args.cmd == "painel":
        from sddtrack import painel
        painel.servir(cfg, args.porta, abrir=not args.sem_abrir)
    elif args.cmd == "sync":
        sync(cfg, args)
    elif args.cmd == "status":
        e = sync(cfg, args, silencioso=True)  # status sempre reflete o código de agora
        if args.json:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        else:
            mostrar_status(e, detalhado=not args.resumo)
    elif args.cmd == "go":
        curador.ir_para(args.task, lambda: sync(cfg, args, silencioso=True), interativo=not args.sem_perguntar)
    elif args.cmd == "proxima":
        e = sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)
        for i in curador.proximas(e):
            print(curador.detalhe(e, i))
    elif args.cmd == "pendentes":
        e = sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)
        if args.json:
            print(json.dumps(e["pendentes_ia"], ensure_ascii=False, indent=2))
        for p in ([] if args.json else e["pendentes_ia"]):
            print(f"\n{p['chave']} ({p['motivo']}): {p['descricao']}")
            for n in p["candidatos"][:15]:
                print("   -", n)
        if not e["pendentes_ia"] and not args.json:
            print("Nada pendente de julgamento.")
    elif args.cmd == "trecho":
        sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)
        nos = est_codigo(cfg)
        if args.no not in nos:
            raise SystemExit(f"Nó inexistente: {args.no}")
        print(indexer.trecho(cfg["projeto"], nos[args.no], max_linhas=200))
    elif args.cmd in ("link", "nao-feito", "unlink"):
        sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)  # hashes e pendências atuais
        with est.trava(cfg):
            manuais, negativos = est.carregar_manuais(cfg), est.carregar_negativos(cfg)
            if args.cmd == "link":
                nos = est_codigo(cfg)
                faltam = [n for n in args.nos if n not in nos]
                if faltam:
                    raise SystemExit(f"Nós inexistentes (não invente ids): {faltam}")
                manuais[args.alvo] = {n: nos[n]["hash"] for n in args.nos}
                negativos.pop(args.alvo, None)
            elif args.cmd == "nao-feito":
                pend = [p for p in engine_pendentes(cfg) if p["chave"] == args.alvo]
                if not pend:
                    raise SystemExit("Esse critério não está pendente.")
                negativos[args.alvo] = engine._fp_cand(pend[0]["candidatos"], est_codigo(cfg))
            else:
                manuais.pop(args.alvo, None)
                negativos.pop(args.alvo, None)
            est.salvar_manuais(cfg, manuais)
            est.salvar_negativos(cfg, negativos)
        print("Registrado. Rode `status` para ver o efeito.")
    elif args.cmd == "watch":
        ultimo = None
        print("Vigiando o projeto (Ctrl+C para sair)…")
        while True:
            spec = spec_mod.carregar(cfg["specs"])
            fp = (indexer.indexar(cfg["projeto"], spec["ignorar"])["fp"], spec["hash"])
            if fp != ultimo:  # só reanalisa se algo mudou
                ultimo = fp
                novo = sync(cfg, args, silencioso=True)
                print(time.strftime("%H:%M:%S"), f"{novo['resumo']['progresso_tasks']:.0%}", *novo["mudancas"], sep="  ")
            time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
