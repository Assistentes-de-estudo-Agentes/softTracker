#!/usr/bin/env python3
"""Harness de acompanhamento: vincula a especificação ao código e mostra o que está feito e o que falta."""
import argparse
import json
import os
import shutil
import sys
import time

from sddtrack import curador, engine, estado as est, indexer, spec as spec_mod, test_runner
from sddtrack.curador import SIMB


def carregar_cfg(caminho):
    if not os.path.exists(caminho):
        raise SystemExit("Configuração ausente. Inicialize primeiro com: python harness.py init --projeto CAMINHO_DO_PROJETO --spec CAMINHO_DA_ESPECIFICACAO")
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(caminho))

    def relativo_ao_config(valor):
        if not valor:
            return valor
        valor = os.path.expandvars(os.path.expanduser(str(valor)))
        return os.path.abspath(valor if os.path.isabs(valor) else os.path.join(base, valor))

    cfg["projeto"] = relativo_ao_config(cfg.get("projeto"))
    cfg["specs"] = [relativo_ao_config(p) for p in (cfg.get("specs") or [])]
    cfg["estado"] = relativo_ao_config(cfg.get("estado", "estado"))
    if not cfg["projeto"] or not os.path.isdir(cfg["projeto"]):
        raise SystemExit(f"Diretório do projeto não encontrado: {cfg.get('projeto')}. Reconfigure com `python harness.py init`. ")
    if not cfg["specs"]:
        raise SystemExit("Nenhuma especificação configurada. Execute `python harness.py init --projeto ... --spec ...`.")
    ausentes = [p for p in cfg["specs"] if not os.path.isfile(p)]
    if ausentes:
        raise SystemExit("Arquivo(s) de especificação não encontrado(s):\n  " + "\n  ".join(ausentes))
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
    vt = e.get("validacao_testes") or {}
    if vt.get("total"):
        print(f"\nTestes vinculados: {vt.get('aprovados', 0)}/{vt.get('total', 0)} aprovados; "
              f"{vt.get('falhos', 0)} falhos; {vt.get('desatualizados', 0)} desatualizados; "
              f"{vt.get('nao_executados', 0)} não executados.")
        if vt.get("ultima_execucao"):
            print(f"Última execução de testes: {vt['ultima_execucao']} ({vt.get('estado_ultima_execucao', 'desconhecido')}).")
        elif vt.get("habilitado"):
            print("Execute `python harness.py testar` para validar o comportamento configurado.")
    for a in e["avisos"]:
        print("⚠", a)


def modo_padrao(args, ap):
    if not os.path.exists(args.config):
        print(
            "SoftTracker ainda não foi configurado. Escolha um único diretório de código e a especificação "
            "que descreve esse mesmo projeto.\n\n"
            "  python harness.py init --projeto CAMINHO_DO_PROJETO --spec CAMINHO_DA_ESPECIFICACAO\n\n"
            "Você pode usar caminhos absolutos ou relativos. Nenhum projeto-alvo vem incluído no pacote.\n"
        )
        ap.print_help()
        raise SystemExit(1)
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
    p = sub.add_parser("init", help="configura um único projeto-alvo e sua especificação")
    p.add_argument("--projeto", required=True, help="caminho para o único diretório de código monitorado")
    p.add_argument("--spec", nargs="+", required=True, help="uma ou mais especificações do mesmo projeto")
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
    sub.add_parser("validar", help="valida o manifesto, vínculos e configuração dos testes")
    p = sub.add_parser("testar", help="executa os testes configurados do projeto-alvo e associa resultados aos critérios")
    p.add_argument("--impactados", action="store_true", help="executa somente testes não executados, falhos ou desatualizados segundo seus fingerprints")
    p.add_argument("--json", action="store_true", help="imprime o relatório da execução em JSON")
    p = sub.add_parser("painel", help="abre o painel local no navegador")
    p.add_argument("--porta", type=int, default=8765)
    p.add_argument("--sem-abrir", action="store_true")
    p = sub.add_parser("pendentes", help="critérios que precisam de julgamento (para o agente)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("trecho", help="imprime o código de um nó")
    p.add_argument("no")
    p = sub.add_parser("link", help="registra que o critério é atendido por estes nós")
    p.add_argument("alvo", help="ID_DA_TASK/ID_DO_CRITERIO (IDs usados na especificação ativa)")
    p.add_argument("nos", nargs="+", help="ids de nó existentes (veja `pendentes` ou estado/codigo.json)")
    p = sub.add_parser("nao-feito", help="registra que os candidatos atuais NÃO atendem o critério")
    p.add_argument("alvo")
    p = sub.add_parser("unlink")
    p.add_argument("alvo")
    args = ap.parse_args()

    if args.cmd is None:  # sem subcomando: abre o painel do projeto atualmente configurado
        modo_padrao(args, ap)
        return
    if args.cmd == "init":
        caminho_config = os.path.abspath(args.config)
        pasta_config = os.path.dirname(caminho_config)
        projeto_novo = os.path.realpath(os.path.expanduser(args.projeto))
        specs_novas = [os.path.realpath(os.path.expanduser(s)) for s in args.spec]
        if not os.path.isdir(projeto_novo):
            raise SystemExit(f"Diretório do projeto não encontrado: {projeto_novo}")
        ausentes = [s for s in specs_novas if not os.path.isfile(s)]
        if ausentes:
            raise SystemExit("Arquivo(s) de especificação não encontrado(s):\n  " + "\n  ".join(ausentes))
        if len(set(specs_novas)) != len(specs_novas):
            raise SystemExit("A mesma especificação foi informada mais de uma vez.")

        # Uma configuração acompanha um único projeto. Se o alvo mudar, apague o
        # estado gerado padrão para não misturar grafos, vínculos e resultados antigos.
        projeto_anterior = None
        estado_anterior_padrao = False
        if os.path.isfile(caminho_config):
            try:
                with open(caminho_config, encoding="utf-8") as f:
                    cfg_anterior = json.load(f)
                valor_anterior = cfg_anterior.get("projeto")
                if valor_anterior:
                    valor_anterior = os.path.expanduser(str(valor_anterior))
                    if not os.path.isabs(valor_anterior):
                        valor_anterior = os.path.join(pasta_config, valor_anterior)
                    projeto_anterior = os.path.realpath(valor_anterior)
                estado_anterior_padrao = cfg_anterior.get("estado", "estado") == "estado"
            except (OSError, json.JSONDecodeError, AttributeError):
                pass

        trocando_alvo = bool(projeto_anterior and projeto_anterior != projeto_novo)
        pasta_estado_padrao = os.path.join(pasta_config, "estado")
        if trocando_alvo and estado_anterior_padrao and os.path.isdir(pasta_estado_padrao):
            shutil.rmtree(pasta_estado_padrao)
            print("Estado gerado do projeto anterior removido para evitar misturar projetos.")

        cfg = {"projeto": projeto_novo, "specs": specs_novas, "estado": "estado"}
        os.makedirs(pasta_config, exist_ok=True)
        temporario = caminho_config + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(temporario, caminho_config)
        print("Configuração gravada em", caminho_config)
        print("Projeto ativo:", projeto_novo)
        print("Especificação(ões):", ", ".join(specs_novas))
        print("Apenas este projeto será acompanhado por esta configuração.")
        return
    cfg = carregar_cfg(args.config)

    if args.cmd == "validar":
        spec_atual = spec_mod.carregar(cfg["specs"])
        erros, avisos = spec_mod.validar(spec_atual)
        erros_testes, avisos_testes = test_runner.validar_config(cfg, spec_atual)
        erros.extend(erros_testes)
        avisos.extend(avisos_testes)
        for m in erros:
            print("✘", m)
        for m in avisos:
            print("⚠", m)
        print("Manifesto e configuração válidos." if not erros else f"{len(erros)} erro(s).")
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
    elif args.cmd == "testar":
        # Sync prévio atualiza o índice e identifica resultados velhos antes da execução.
        e = sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)
        spec_atual = spec_mod.carregar(cfg["specs"])
        ids_configurados = sorted(test_runner.testes_por_criterio(spec_atual))
        if args.impactados:
            estados_testes = (e.get("validacao_testes") or {}).get("testes", {})
            pendentes = {tid for tid, item in estados_testes.items()
                         if item.get("estado") != "aprovado"}
            # A validade por teste é a fonte da verdade para a execução seletiva.
            # O impacto do grafo é informativo e pode ser conservador; uni-lo aqui
            # faria um arquivo compartilhado disparar testes que continuam atuais.
            selecionados = sorted(pendentes & set(ids_configurados))
            if not selecionados:
                print("Nenhum teste impactado ou desatualizado. Nada foi executado.")
                return
        else:
            selecionados = None
        conf_testes = test_runner.configuracao(cfg)
        fps_atuais = test_runner.fingerprints(spec_atual, e["tasks"], est.carregar_codigo(cfg),
                                             cfg["projeto"], conf_testes)
        try:
            execucao = test_runner.executar(cfg, selecionados)
        except test_runner.ErroConfiguracaoTestes as exc:
            raise SystemExit(f"Configuração de testes inválida: {exc}")
        armazenamento = test_runner.mesclar_resultados(est.carregar_testes(cfg), execucao, fps_atuais)
        with est.trava(cfg):
            est.salvar_testes(cfg, armazenamento)
        final = sync(cfg, argparse.Namespace(ia_api=False, max_ia=0), silencioso=True)
        if args.json:
            print(json.dumps({"execucao": execucao, "validacao": final.get("validacao_testes", {})},
                             ensure_ascii=False, indent=2))
        else:
            resumo = execucao.get("resultados", {})
            print(f"Execução: {execucao.get('estado_execucao')} · {execucao.get('duracao_segundos', 0)} s")
            print(f"Comando: {' '.join(execucao.get('comando') or [])}")
            for tid, item in resumo.items():
                print(f"  {item.get('estado', 'desconhecido'):16} {tid}" +
                      (f" — {item.get('mensagem', '')[:180]}" if item.get("mensagem") else ""))
            vt = final.get("validacao_testes") or {}
            print(f"Validação atual: {vt.get('aprovados', 0)}/{vt.get('total', 0)} testes aprovados; "
                  f"{vt.get('falhos', 0)} falhos; {vt.get('desatualizados', 0)} desatualizados.")
        if execucao.get("estado_execucao") != "aprovado" or any(
                x.get("estado") != "aprovado" for x in (execucao.get("resultados") or {}).values()):
            raise SystemExit(1)
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
            cache_codigo = est.carregar_codigo(cfg)
            fp = (indexer.indexar(cfg["projeto"], spec["ignorar"], anterior=cache_codigo)["fp"], spec["hash"])
            if fp != ultimo:  # só reanalisa se algo mudou
                ultimo = fp
                novo = sync(cfg, args, silencioso=True)
                print(time.strftime("%H:%M:%S"), f"{novo['resumo']['progresso_tasks']:.0%}", *novo["mudancas"], sep="  ")
            time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
