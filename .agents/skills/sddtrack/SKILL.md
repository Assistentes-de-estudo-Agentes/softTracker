---
name: sddtrack
description: Acompanha o desenvolvimento do projeto vinculando a especificação (tasks, critérios, casos de uso, UML) ao código da pasta projeto/. Use quando o usuário perguntar o que já foi feito ou falta, escolher/ir para uma task, pedir status ou progresso, atualizar a análise, ou quando um critério precisar de julgamento.
---

# sddtrack — spec ↔ código

Você é o curador. O script `harness.py` (na raiz do workspace) faz a parte determinística; **você faz o julgamento e a conversa**.
Use `python3` (ou `python` no Windows). Rode sempre da raiz do workspace.

## Regras
- Existir no código do projeto = feito. Tudo que está em `projeto/` já foi revisado: **não rode testes, não leia CI, não valide qualidade**.
- **Nunca edite** arquivos de `projeto/` nem de `estado/` à mão. Só use os comandos abaixo.
- **Nunca invente ids de nó.** Só use ids vindos de `pendentes` ou de `estado/codigo.json`.
- Não gere código a menos que o usuário peça explicitamente; seu papel aqui é só informar.
- Ao dar status, **rode `status` antes** (reflete o código de agora); não responda de memória.

## Comandos
- `python3 harness.py status` — sincroniza e mostra barra, blocos e critérios (`--resumo` para curto, `--json` para dados).
- `python3 harness.py pendentes` — critérios que precisam do seu julgamento, com nós candidatos.
- `python3 harness.py trecho "<id do nó>"` — mostra o código do nó.
- `python3 harness.py link TASK-001/C1 "<nó>" ["<nó>" ...]` — registra que o critério é atendido por esses nós.
- `python3 harness.py nao-feito TASK-001/C1` — registra que os candidatos atuais NÃO atendem.
- `python3 harness.py unlink TASK-001/C1` — desfaz um vínculo ou julgamento.
- `python3 harness.py go TASK-005 --sem-perguntar` — mostra pendências anteriores da task.
- `python3 harness.py proxima` — tasks que já podem começar.
- `python3 harness.py validar` — valida o manifesto (`spec/`).
- Primeira vez: `python3 harness.py init --projeto projeto --spec spec/<arquivo>`.

## Fluxo: julgar pendências
1. Rode `pendentes`. Para cada critério listado, leia os candidatos com `trecho`.
2. O código cumpre a **descrição do critério**? Se sim → `link` com os nós que provam. Se não → `nao-feito`.
3. `motivo: codigo_mudou` significa que o código vinculado mudou: releia e confirme com `link` (atualiza) ou refute com `unlink` + `nao-feito`.
4. Em caso de dúvida real, pergunte ao usuário em vez de adivinhar.
5. Rode `status --resumo` e relate o que mudou.

## Fluxo: usuário escolhe uma task ("quero fazer a TASK-005")
1. Rode `go TASK-005 --sem-perguntar`. Se houver pendências, **pergunte no chat** e espere a resposta:
   1. fazer a anterior primeiro (mostre qual e quais critérios faltam);
   2. atualizar a análise (rode `status` de novo — alguém pode já ter feito) e reavaliar;
   3. seguir mesmo assim, registrando o risco.
2. Sem pendências, mostre os critérios da task e o que falta.
3. Se o usuário disser que outra pessoa fez algo: opção 2 (re-sincronizar), nunca assuma.

## Ao relatar status
Mostre: progresso (tasks e critérios), o que mudou desde antes, próximas tasks liberadas, avisos (`⚠`) e código sem task.
Os dados para o painel ficam em `estado/status.json` (não altere).
