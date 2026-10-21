# Capacidades e correções incluídas

## Rastreamento mais confiável

- Comentários de linha e bloco são ignorados na análise de símbolos, rotas e evidências textuais.
- Critérios de conteúdo podem ser limitados a um método, classe, rota ou símbolo, evitando que a evidência de uma funcionalidade satisfaça outra por estar no mesmo arquivo.
- O indexador reconhece construções e rotas de várias linguagens e frameworks suportados, combinando escopos quando aplicável.
- O grafo associa requisitos, casos de uso, tarefas, critérios, arquivos e símbolos e usa relações reversas para estimar o impacto de alterações.
- Caminhos de configuração são resolvidos de forma previsível, sem depender de diretórios absolutos de uma máquina específica.
- Cada `harness.json` monitora um único diretório de projeto-alvo. Ao reconfigurar para outro diretório, o estado padrão do alvo anterior é limpo para evitar contaminação de vínculos e resultados.

## Validação comportamental opcional

- O comando `testar` executa somente comandos explicitamente configurados.
- O executor aplica timeout, usa argumentos sem `shell=True` e interpreta relatórios JUnit XML.
- IDs de teste podem ser vinculados a critérios por meio de `verificacao.testes`.
- Resultados de testes ficam separados do estado da análise estática.
- `testar --impactados` permite reexecutar testes não executados, falhos ou com evidências desatualizadas, desde que o runner suporte filtragem pelo marcador `{pattern}`.
- Fingerprints consideram critérios vinculados, símbolos relacionados, arquivos de teste e configuração do executor.

## Configuração limpa

- O pacote não inclui projeto-alvo, aplicação de demonstração, especificação vinculada a um produto específico, configuração `harness.json` nem estado gerado.
- A primeira execução começa pela configuração explícita de um único projeto e sua especificação com `python harness.py init --projeto CAMINHO_DO_PROJETO --spec CAMINHO_DA_ESPECIFICACAO`.
- A ferramenta pode monitorar diferentes linguagens/projetos, conforme os recursos do indexador e a configuração fornecida; não garante suporte semântico completo a toda linguagem ou framework.

## Limitações importantes

- A validação comportamental precisa ser configurada para a aplicação e a ferramenta de testes do usuário.
- O indexador e o grafo fornecem evidências heurísticas; não substituem a execução de testes nem a revisão de critérios complexos.
