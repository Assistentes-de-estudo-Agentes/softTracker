# softTracker - Acompanhe o desenvolvimento do seu projeto.
**Acompanhe requisitos, tarefas e evidências do código em um único painel.**

O **SDDTrack** é um harness de *Specification-Driven Development* (SDD) com dashboard local. Ele conecta o que foi especificado para um software — requisitos, casos de uso, tarefas e critérios de aceitação — aos sinais encontrados no código-fonte. Assim, fica mais fácil entender o que já tem evidência de implementação, o que está parcial e o que ainda precisa de atenção.

> **Importante:** o SDDTrack analisa especificações e código; não substitui testes automatizados, revisão humana nem validação em execução. Uma evidência encontrada no código não garante, por si só, que a funcionalidade esteja correta.

## Visão do painel

![Dashboard do SDDTrack](docs/images/dashboard.png)

O painel organiza as informações em áreas fáceis de consultar:

- **Visão geral:** progresso calculado a partir das tasks e dos critérios de aceitação.
- **Casos de uso:** agrupamento das tarefas por funcionalidade.
- **Grafo de tasks:** visualização das tarefas e de seus estados; selecione um nó para ver seus critérios e dependências.
- **Requisitos:** consulta dos requisitos definidos no manifesto.
- **Contexto do projeto:** resumo do estado sincronizado, arquivos analisados, nós de código e critérios que ainda precisam de julgamento.

Os números e indicadores refletem a última sincronização com os arquivos locais. O painel não é um serviço hospedado: ele roda no próprio computador.

## Por que usar?

- **Visibilidade rápida:** veja o que está feito, parcial ou pendente sem precisar cruzar manualmente vários arquivos.
- **Especificação ligada à implementação:** critérios podem apontar para rotas, funções, classes, arquivos ou outros símbolos esperados.
- **Menos acompanhamento manual:** o estado é recalculado a partir do código e da especificação atual.
- **Dependências explícitas:** entenda o que precisa vir antes de começar uma tarefa.
- **Detecção de stack:** identifica tecnologias prováveis a partir de arquivos de configuração e do código.
- **Configuração simples:** a especificação fica em YAML ou JSON, editável com qualquer editor de texto.
- **IA opcional:** critérios que não podem ser julgados por padrões diretos podem ficar pendentes para análise humana/agente; a integração com a API da Anthropic é opcional.
- **Dados locais:** o projeto e o dashboard são executados localmente, sem exigir uma conta ou um serviço remoto para o fluxo básico.

## Como funciona

Em linhas gerais, o fluxo é:

1. Você descreve o projeto em um manifesto (`spec/spec.yaml`): requisitos, casos de uso, tasks e critérios de aceitação.
2. Coloca o código que deseja acompanhar dentro de `projeto/` — ou configura outro diretório.
3. O indexador percorre os arquivos relevantes e identifica elementos como arquivos, funções, classes e rotas, conforme a linguagem.
4. O motor compara os elementos encontrados com os critérios da especificação e registra as evidências correspondentes.
5. O estado é salvo em `estado/status.json` e `estado/codigo.json`.
6. O dashboard lê esse estado e apresenta o progresso, as dependências e os pontos que merecem revisão.

### Como as árvores/grafos são usados

O SDDTrack usa estruturas em grafo para representar relações que ficariam difíceis de entender em uma lista simples:

- **Árvore de dependências das tasks:** cada tarefa pode declarar `depende_de`. Na prática, isso forma um grafo direcionado de dependências (idealmente sem ciclos), permitindo identificar tarefas bloqueadas e sugerir quais podem começar. Uma tarefa só aparece como pronta para começar quando suas dependências estão concluídas.
- **Grafo/índice do código:** arquivos e elementos encontrados no código são indexados como nós. Os critérios podem ser relacionados a esses nós, mantendo evidências que ajudam a explicar por que um critério foi considerado atendido.

O projeto valida dependências inexistentes e ciclos entre tasks. O grafo é uma representação das relações declaradas e identificadas — não uma prova formal de correção do software.

## Comece em poucos minutos

### Requisitos

- Python **3.9 ou superior**.
- `PyYAML` para ler especificações em YAML.
- Windows, macOS ou Linux. O arquivo `.bat` incluído é específico do Windows; em outros sistemas, use o comando Python diretamente.

### 1. Baixe o projeto

Clone o repositório ou baixe o ZIP e abra um terminal na pasta raiz do SDDTrack.

### 2. Instale a dependência

```bash
python -m pip install pyyaml
```

Se você usar apenas um manifesto JSON, a leitura do manifesto não precisa do PyYAML; o exemplo inicial, porém, usa YAML.

### 3. Adicione o código que quer acompanhar

Copie o código-fonte da aplicação para `projeto/`. **Não coloque o próprio SDDTrack nessa pasta**, a menos que queira monitorá-lo deliberadamente.

### 4. Preencha a especificação

Edite `spec/spec.yaml`. O arquivo vem intencionalmente sem tasks de exemplo para que o painel não apresente dados fictícios como se fossem progresso real. Você pode consultar `exemplos/spec-quadro-equipe.yaml` como referência.

Exemplo mínimo:

```yaml
projeto: Minha aplicação

ignorar:
  - "*.md"
  - "tests/**"

requisitos:
  - id: REQ-001
    titulo: Usuário consegue entrar no sistema

casos_de_uso:
  - id: UC-001
    titulo: Autenticação
    requisitos: [REQ-001]

uml: []

tasks:
  - id: TASK-001
    titulo: Criar endpoint de login
    caso_de_uso: UC-001
    criterios:
      - id: C1
        descricao: Existe uma rota POST /login
        artefato:
          tipo: rota
          padrao: "POST /login"
```

Um critério pode ter um `artefato` esperado. Os tipos aceitos incluem `rota`, `funcao`, `classe`, `arquivo` e `simbolo`. O campo `padrao` descreve o nome ou padrão que o indexador deve procurar. Para critérios sem artefato explícito, o harness pode registrá-los para julgamento por agente ou pela IA opcional.

### 5. Valide e sincronize

Execute os comandos na raiz do repositório:

```bash
python harness.py validar
python harness.py sync
python harness.py status
```

- `validar`: verifica IDs, referências, critérios e dependências.
- `sync`: reanalisa o código e atualiza as evidências e o estado.
- `status`: mostra o progresso no terminal.

### 6. Abra o dashboard

**Windows:** dê dois cliques em `iniciar_dashboard.bat`.

**Qualquer sistema com Python:**

```bash
python dashboard.py
```

O navegador será aberto automaticamente. Se necessário, copie o endereço mostrado no terminal (normalmente `http://127.0.0.1:8765`). O servidor procura outra porta livre caso a padrão já esteja ocupada. Para encerrar, pressione `Ctrl+C` no terminal.

Depois de alterar o código ou a especificação, use **Sincronizar** no painel para atualizar o estado.

## Estados das tarefas

| Estado | Significado |
| --- | --- |
| **Feita** | Todos os critérios de aceitação têm evidência considerada atendida. |
| **Parcial** | Há critérios atendidos, mas ainda faltam outros. |
| **Não feita** | Nenhum critério está atendido. |
| **Revalidar** | Uma evidência vinculada mudou e precisa ser revisada. |

O progresso exibido é calculado a partir das tasks e dos critérios presentes na especificação. Se não houver tasks cadastradas, é esperado que o painel mostre zero progresso — isso não significa que o código analisado esteja necessariamente vazio.

## Comandos úteis

```bash
python harness.py validar
python harness.py sync
python harness.py status --resumo
python harness.py status --json
python harness.py proxima
python harness.py go TASK-001
python harness.py watch
python harness.py pendentes
```

- `proxima`: lista tasks cujas dependências já foram concluídas.
- `go TASK-001`: leva à tarefa escolhida e mostra pendências anteriores.
- `watch`: monitora alterações no código e na especificação periodicamente (`Ctrl+C` para parar).
- `pendentes`: lista critérios que precisam de julgamento.
- `trecho ID_DO_NO`: exibe o trecho de código de um nó indexado.
- `link TASK-001/C1 ID_DO_NO`: registra um vínculo manual entre um critério e um nó de código existente.
- `unlink TASK-001/C1`: remove o vínculo manual.
- `--simular` em `sync`: permite inspecionar mudanças sem gravar o novo estado.

Use `python harness.py --help` e `python harness.py COMANDO --help` para consultar as opções disponíveis.

## Configuração

O arquivo `harness.json` define:

```json
{
  "projeto": "projeto",
  "specs": ["spec/spec.yaml"],
  "estado": "estado"
}
```

- `projeto`: caminho para o código que será analisado.
- `specs`: lista de manifestos YAML/JSON. É possível combinar vários arquivos.
- `estado`: diretório onde os estados e vínculos serão salvos.

Os caminhos relativos são interpretados a partir da pasta de execução para os comandos do harness; execute-os a partir da raiz do repositório. Para registrar caminhos absolutos diferentes, use:

```bash
python harness.py init --projeto CAMINHO_DO_CODIGO --spec CAMINHO_DA_SPEC
```

Esse comando grava a configuração no `harness.json` indicado por `--config` (por padrão, na pasta atual).

## Detecção de tecnologias

O detector procura indícios em arquivos de configuração, extensões e código — por exemplo, `package.json`, `requirements.txt`, `pom.xml`, `build.gradle`, `go.mod` e arquivos de projeto .NET. A detecção é heurística: mostra tecnologias prováveis, mas não comprova que dependências estejam instaladas, que serviços estejam rodando ou que a aplicação esteja funcionando.

## IA (opcional)

O uso básico não exige chave de API. A integração opcional com a API da Anthropic pode ajudar a julgar critérios sem um padrão de artefato direto. Para ativá-la, configure `ANTHROPIC_API_KEY` no ambiente e, se necessário, `HARNESS_MODEL`, e execute a sincronização com `--ia-api`.

A API pode gerar custos conforme o modelo e o uso. Sem chave ou sem habilitar a opção, os critérios ambíguos ficam sinalizados como pendentes para julgamento pelo agente ou por uma pessoa.

## Estrutura do projeto

```text
SDDTrack/
├── .agents/                  # Instruções e workflows para agentes
├── dashboard/
│   ├── index.html             # Interface do painel
│   ├── style.css              # Estilos
│   └── app.js                 # Interações e renderização
├── docs/
│   └── images/
│       └── dashboard.png      # Captura do painel incluída neste README
├── exemplos/
│   └── spec-quadro-equipe.yaml
├── projeto/                   # Código da aplicação monitorada
├── sddtrack/
│   ├── curador.py             # Navegação por tasks e dependências
│   ├── engine.py              # Sincronização e avaliação de critérios
│   ├── estado.py              # Persistência do estado
│   ├── indexer.py             # Indexação do código-fonte
│   ├── llm.py                 # Integração opcional com IA
│   ├── spec.py                # Leitura e validação da especificação
│   └── stack_detector.py      # Detecção heurística de tecnologias
├── spec/
│   └── spec.yaml              # Especificação do projeto monitorado
├── estado/                    # Estado gerado durante a execução
├── dashboard.py               # Servidor local do dashboard
├── harness.py                 # Interface de linha de comando
├── harness.json               # Configuração do harness
└── iniciar_dashboard.bat       # Inicialização rápida no Windows
```

## Limitações conhecidas

- O dashboard é **local** e fica disponível enquanto o processo Python estiver em execução; não é hospedado na nuvem.
- O painel é principalmente de consulta e visualização. A edição da especificação acontece nos arquivos YAML/JSON.
- A análise é estática e baseada em padrões/evidências; não executa automaticamente a suíte de testes nem garante comportamento em runtime.
- A detecção da stack é heurística e pode deixar de reconhecer tecnologias ou sugerir uma identificação que precise ser conferida.
- A integração direta com a API da Anthropic é opcional e depende de conexão, chave válida e disponibilidade do serviço.

## Contribuindo

Sugestões, correções e melhorias são bem-vindas. Para contribuir:

1. Abra uma issue descrevendo o problema ou a ideia.
2. Para mudanças maiores, explique a abordagem antes de implementar.
3. Mantenha exemplos e documentação alinhados ao comportamento real do código.
4. Evite incluir chaves de API, credenciais ou dados sensíveis em commits.

## Licença

Distribuído sob a licença [MIT](LICENSE).
