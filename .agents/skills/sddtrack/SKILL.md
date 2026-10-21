---
name: sddtrack
description: Acompanha o desenvolvimento relacionando critérios de aceitação, requisitos, casos de uso, tasks e evidências do código. Use para analisar progresso, pendências e impacto de alterações.
---

# sddtrack — rastreabilidade entre especificação e código

O `harness.py` faz a análise estrutural e mantém um grafo local de rastreabilidade. O agente deve revisar semanticamente os critérios sem evidência determinística, e nunca confundir nome de símbolo com comportamento comprovado.

## Princípios
- Uma rota, classe ou função encontrada é evidência estrutural, não prova automática de que todos os critérios funcionais foram atendidos.
- Critérios sem artefato determinístico exigem leitura dos candidatos e julgamento explícito.
- Não invente IDs de nós: use os resultados de `pendentes` ou `estado/codigo.json`.
- Ao revisar um critério, leia o trecho e considere código relacionado; não conclua só pelo nome da função.
- Não altere manualmente `estado/`. Mudanças de vínculos devem usar os comandos do harness.
- Sempre rode `status` depois de mudanças relevantes, para recalcular as evidências e o impacto.

## Comandos
- `python harness.py status` — sincroniza e mostra status, critérios e alertas.
- `python harness.py status --json` — saída completa, incluindo grafo de rastreabilidade e impacto de código.
- `python harness.py pendentes` — critérios sem conclusão semântica e candidatos relevantes.
- `python harness.py trecho "<id do nó>"` — mostra o trecho indexado de código.
- `python harness.py link <ID_TASK>/<ID_CRITERIO> "<nó>" ["<nó>" ...]` — confirma um vínculo após revisão.
- `python harness.py nao-feito <ID_TASK>/<ID_CRITERIO>` — registra que os candidatos atuais não atendem ao critério.
- `python harness.py unlink <ID_TASK>/<ID_CRITERIO>` — remove o julgamento anterior.
- `python harness.py proxima` — mostra tasks desbloqueadas por suas dependências.
- `python harness.py validar` — valida o manifesto.
- `python harness.py painel` — abre o painel local.

## Fluxo de revisão
1. Rode `pendentes`.
2. Leia os trechos dos nós candidatos e siga as chamadas/importações relevantes.
3. Compare o comportamento com a descrição do critério e todos os seus critérios de aceitação.
4. Se as evidências sustentarem o critério, use `link`; se não sustentarem, use `nao-feito`.
5. Rode `status` e explique as evidências, incertezas e o que mudou.

## Interpretação do status
- `feita`: todos os critérios têm evidências consideradas atendidas.
- `parcial`: apenas parte dos critérios está atendida.
- `nao_feita`: nenhum critério está confirmado.
- `revalidar`: uma evidência anteriormente julgada mudou e precisa de nova revisão.

O grafo ajuda a navegar dependências e a calcular impacto; ele não substitui análise semântica nem testes automatizados.
