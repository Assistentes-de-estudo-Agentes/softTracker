# SoftTracker — rastreabilidade entre especificação e código

O SoftTracker é uma ferramenta local para acompanhar a implementação de requisitos, casos de uso, tarefas e critérios de aceitação em **um único projeto de software por configuração**. Ele não inclui uma aplicação-alvo, linguagem obrigatória, especificação de exemplo nem configuração vinculada a um projeto preexistente. Você escolhe o projeto que deseja monitorar.

A análise estática e a validação comportamental são dimensões separadas: encontrar código compatível não significa, por si só, que o comportamento foi comprovado por testes.

## Requisitos

- Python 3.9 ou superior. A versão do pacote foi exercitada com Python 3.13.5; a faixa completa do Python 3.9+ não foi testada integralmente.
- PyYAML para ler especificações `.yml`/`.yaml` (`pip install pyyaml`). Especificações JSON não exigem essa dependência.
- Um navegador moderno para abrir o painel local.
- Para execução comportamental, a ferramenta de testes usada pelo projeto-alvo e uma configuração explícita do executor.

## Começar: configure um projeto

O pacote começa **sem projeto-alvo e sem manifesto pré-selecionado**. Isso evita analisar por engano um projeto de demonstração ou misturar dados de aplicações diferentes.

1. Escolha o diretório do código que deseja acompanhar.
2. Prepare uma especificação YAML ou JSON que descreva esse mesmo projeto e inclua tarefas com critérios de aceitação.
3. Na pasta do SoftTracker, execute `init` apontando para esse diretório e para a especificação:

```bash
python harness.py init --projeto "CAMINHO_DO_PROJETO" --spec "CAMINHO_DA_ESPECIFICACAO.yml"
python harness.py validar
python harness.py status --resumo
python harness.py painel
```

Substitua os caminhos de exemplo pelos caminhos reais do seu computador. Tanto caminhos absolutos quanto relativos são aceitos. Se a especificação estiver em JSON, use o caminho `.json`. Você também pode informar vários arquivos de especificação com `--spec`, desde que todos descrevam **o mesmo projeto-alvo**.

O comando `init` cria `harness.json` com o único diretório de código ativo e os arquivos de especificação escolhidos. O estado gerado fica na pasta `estado/` ao lado da configuração. Se você reconfigurar o mesmo `harness.json` para outro diretório de projeto, o estado gerado padrão anterior é limpo para evitar misturar grafos, vínculos manuais e resultados de testes de projetos distintos.

Depois de configurar, pode iniciar o painel com `python harness.py painel` ou, no Windows, com `iniciar_dashboard.bat`. Para abrir o painel sem iniciar automaticamente o navegador:

```bash
python harness.py painel --porta 8765 --sem-abrir
```

Depois acesse `http://localhost:8765`.

### Requisitos mínimos da especificação

A especificação deve ter IDs estáveis, tarefas (`tasks` ou `tarefas_desenvolvimento`) e critérios de aceitação não vazios. Os artefatos opcionais ajudam a vincular critérios ao código. Exemplo genérico de estrutura (substitua os nomes e os critérios pelos do seu sistema):

```yaml
projeto:
  nome: "Nome do seu sistema"

requisitos:
  - id: RF001
    titulo: "Descrição do requisito"
    tipo: funcional

casos_de_uso:
  - id: UC001
    titulo: "Fluxo relacionado ao requisito"
    requisitos: [RF001]

tasks:
  - id: T001
    titulo: "Implementar o comportamento exigido"
    casos_de_uso: [UC001]
    depende_de: []
    criterios:
      - id: C1
        descricao: "Resultado verificável esperado"
        artefato:
          tipo: funcao
          padrao: "nomeDaFuncao"
```

Tipos de artefato aceitos incluem `rota`, `funcao`, `classe`, `arquivo`, `simbolo` e `conteudo`. Um artefato é uma pista rastreável, não uma prova automática de que a funcionalidade funciona. Critérios complexos devem ser associados a testes comportamentais ou revisados semanticamente.

## Comandos principais

```bash
python harness.py validar
python harness.py sync
python harness.py status --resumo
python harness.py status --json
python harness.py proxima
python harness.py pendentes
python harness.py go ID_DA_TASK
python harness.py link ID_DA_TASK/ID_DO_CRITERIO ID_DO_NO
python harness.py nao-feito ID_DA_TASK/ID_DO_CRITERIO
python harness.py painel
```

Os IDs dos exemplos são marcadores. Use os IDs reais que constam na especificação ativa e os nós exibidos por `pendentes`/`trecho`. Consulte `python harness.py --help` e `python harness.py link --help` para todas as opções.

## Validação comportamental opcional

O executor de testes está integrado, mas não é habilitado por padrão. Para usá-lo, configure a seção `testes` em `harness.json` e vincule IDs estáveis de testes aos critérios por meio de `verificacao.testes`.

Exemplo de configuração do executor (adapte o comando, o diretório e os arquivos à ferramenta real do seu projeto):

```json
{
  "testes": {
    "habilitado": true,
    "comando": ["COMANDO_DO_TEST_RUNNER", "ARGUMENTO_JUNIT"],
    "formato": "junit",
    "diretorio": "CAMINHO_DO_PROJETO",
    "arquivos": ["CAMINHO/DO/ARQUIVO_DE_TESTES"],
    "timeout_segundos": 60,
    "env": {}
  }
}
```

O comando precisa produzir um relatório JUnit XML reconhecível na saída padrão. A opção seletiva `testar --impactados` requer que o comando contenha o marcador `{pattern}` em um argumento e que o runner consiga filtrar pelos IDs de teste. Alguns frameworks gravam relatórios em arquivos; nesses casos, configure um adaptador que emita o relatório no formato esperado.

Depois de configurar o executor e vincular os testes na especificação:

```bash
python harness.py validar
python harness.py testar
python harness.py testar --impactados
python harness.py status --json
```

`status` não executa testes. Ele lê os últimos resultados e compara os fingerprints do código, dos critérios vinculados, dos arquivos de teste e da configuração. Resultados com evidências alteradas são marcados como desatualizados até que os testes sejam executados novamente. A execução é explícita, usa uma lista de argumentos sem `shell=True`, tem timeout e exige `testes.habilitado: true`.

Configure somente comandos de teste confiáveis: um processo de teste executa código do projeto e pode realizar operações no computador. O SoftTracker não habilita a execução comportamental automaticamente.

## Como funciona a rastreabilidade

1. **Normalização e validação:** formatos YAML, JSON e campos legados suportados são convertidos para um modelo comum; IDs e referências são verificados.
2. **Indexação:** arquivos, classes, funções e rotas recebem identificadores e hashes; há regras específicas para várias linguagens e frameworks.
3. **Evidências:** padrões estruturais localizam símbolos, arquivos e rotas; evidências textuais verificam configurações e trechos. Comentários são ignorados, e critérios podem ser limitados ao escopo de um método ou símbolo.
4. **Grafo:** conecta requisitos, casos de uso, tarefas, critérios, símbolos, rotas, arquivos e, quando configurados, testes comportamentais.
5. **Cache incremental:** hashes de arquivos e símbolos permitem reaproveitar informações inalteradas. Mudanças, inclusões e exclusões são detectadas no próximo `status` ou `sync`.
6. **Impacto:** relações reversas ajudam a identificar critérios e testes potencialmente afetados por mudanças, evitando comparar indiscriminadamente todos os requisitos com todos os símbolos.
7. **Validação comportamental:** `sddtrack/test_runner.py` executa o comando configurado, interpreta JUnit XML e armazena os resultados no diretório de estado escolhido pela configuração.

O grafo de chamadas é uma aproximação estática; não resolve perfeitamente métodos dinâmicos, injeção de dependências, sobrecargas ou toda a lógica distribuída entre arquivos. A ausência de correspondência significa “não foi encontrada evidência pelas regras atuais”, não uma prova absoluta de que a funcionalidade inexiste.

## Status e limites

- **Feita:** todos os critérios têm evidências conforme as regras configuradas.
- **Parcial:** alguns critérios têm evidência, mas outros continuam sem comprovação.
- **Não feita / sem evidência:** a análise atual não confirmou nenhum critério da tarefa.
- **Revalidar:** uma evidência previamente revisada mudou e precisa ser reavaliada.

O painel apresenta separadamente o estado estático da implementação e, quando configurado, o estado dos testes: aprovado, falhou, não executado, desatualizado ou incompleto. Padrões de nomes e expressões regulares são heurísticas; testes comportamentais são necessários para comprovar o funcionamento real.
