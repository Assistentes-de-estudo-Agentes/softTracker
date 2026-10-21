# Harness de acompanhamento (spec ↔ código)

Vincula a especificação ao código do projeto e mostra o que está feito e o que falta.
Roda 100% local, só com Python 3.9+ (YAML exige `pip install pyyaml`; JSON não exige nada).
Não roda testes, não lê CI, não gera código: o que está no projeto já foi revisado, então
**existir no código = feito**. Se o código é apagado, a task volta atrás no próximo sync.

## Layout (este diretório é o workspace do Antigravity)
    harness.py  sddtrack/      # o harness
    spec/                      # sua especificação (YAML/JSON)
    projeto/                   # raiz do código (repositório git)
    estado/                    # gerado: status.json (fonte do painel), codigo.json
    .agents/skills/sddtrack/   # skill: ensina o Gemini a operar o harness
    .agents/workflows/         # /status  /ir TASK-005  /atualizar
    .agents/rules/             # regras fixas (não editar projeto/ nem estado/)

## Uso rápido
Atalho: `python harness.py` (sem comando) configura na primeira vez, se achar `spec/` e `projeto/`
ao lado do script, valida a especificação e abre o painel. Os comandos abaixo continuam disponíveis.

    python3 harness.py init --projeto projeto --spec spec/spec.yaml   # uma vez
    python3 harness.py validar     # valida o manifesto
    python3 harness.py status      # sincroniza e mostra barra, blocos e critérios
    python3 harness.py proxima     # tasks que já podem começar
    python3 harness.py go TASK-003 # curadoria (no Antigravity o agente conduz a conversa)
    python3 harness.py pendentes   # critérios que precisam de julgamento do agente
    python3 harness.py trecho "<nó>" ; link TASK/C1 "<nó>" ; nao-feito TASK/C1 ; unlink TASK/C1
    python3 harness.py watch       # reanalisa sozinho quando o código muda
    python3 harness.py painel      # abre o painel no navegador (http://localhost:8765)

No Antigravity: abra esta pasta como workspace e peça em linguagem natural ("o que falta?",
"quero fazer a TASK-005") ou use `/status`, `/ir TASK-005`, `/atualizar`.

## Painel (dashboard local)
    python3 harness.py painel [--porta 8765] [--sem-abrir]
Abre `http://localhost:8765` (só aceita conexões desta máquina). Mostra: barra de progresso do projeto
(um bloco por task, agrupados por caso de uso), blocos de todos os casos de uso, grafo de dependências
entre tasks, stack, e na lateral resumo, filtros por status, "podem começar agora", avisos, requisitos e UML.
Clicar em uma task abre critérios, evidências, dependências e o que ela libera. O painel atualiza sozinho
(a cada 4 s, só reanalisa se o código, a spec ou os vínculos mudaram); apagar código reflete em segundos.
`painel/index.html` é um arquivo único sem dependências externas (funciona offline) e lê `/api/status`.
A stack vem da seção `stack:` do manifesto (veja `spec/spec.yaml`).

Para ver o painel com dados de exemplo:
    python3 harness.py --config demo/harness.json init --projeto demo/projeto --spec spec/spec.yaml
    python3 harness.py --config demo/harness.json painel

## Como funciona
1. `spec.py` lê e valida o manifesto (IDs, referências, ciclos, critérios).
2. `indexer.py` mapeia o código em nós (arquivo, função, classe, rota) com hash — sem IA,
   tolera código incompleto/com erro de sintaxe.
3. `engine.py` recalcula o status de TODOS os critérios a cada sync, a partir do código atual:
   - critério com `artefato` → casado por padrão (grátis, determinístico);
   - critério sem artefato (ou `usar_ia: true` com o padrão sem achar) → vira **pendente**:
     o agente (Gemini) lê os candidatos e decide com `link`/`nao-feito`. Nenhuma API de IA é
     necessária. Um `link` guarda o hash do código julgado; se esse código mudar, o critério
     vira `revalidar` e volta às pendências. Um `nao-feito` só reaparece se os candidatos mudarem;
   - `link` recusa ids de nó que não existem (o agente não consegue inventar vínculo);
   - (opcional) `--ia-api` + `ANTHROPIC_API_KEY` julga por API em vez do agente.
4. Status da task: `feita` (todos os critérios), `parcial`, `nao_feita`, `revalidar`
   (evidência da IA mudou de hash e não pôde ser reavaliada).
5. `curador.py` resolve dependências antes de você começar uma task.

## Saídas (estado/)
- `status.json`: tasks, critérios, evidências, grafo de tasks, UML colorida por status,
  requisitos, progresso, código sem task, avisos. É a fonte do painel.
- `codigo.json`: grafo do código com hashes. `vinculos_manuais.json`: suas correções.

## Manifesto
Veja `exemplo/spec/spec.yaml`. Tipos de artefato: `rota`, `funcao`, `classe`, `arquivo`, `simbolo`.
Padrões usam `*`; nomes ignoram maiúsculas, `_` e `-` (`*hash*senha*` casa `comparar_hash_senha`).
Rotas aceitam `:id`, `{id}` ou `<id>` como curinga. `ignorar:` no manifesto exclui pastas/arquivos.

## Limites conhecidos
- Rotas: prefixo de controller (Nest/Spring) não é somado ao caminho.
- O julgamento pelo agente depende de o Gemini seguir a skill; o harness protege o estado
  (ids inexistentes são recusados), mas não garante que o julgamento esteja certo.
- O painel não abre via arquivo (file://): use `harness.py painel`. Não há edição pelo painel (somente leitura).
- Skill/workflows/rules seguem o formato documentado do Antigravity (`.agents/`), mas não foram
  testados dentro do Antigravity. `llm.py` (API opcional) não foi testado contra a API real.
