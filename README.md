# SDDTrack — harness SDD com dashboard local

O SDDTrack relaciona especificações (requisitos, casos de uso, tasks e critérios de aceitação) com evidências encontradas no código-fonte. O dashboard mostra o estado desse acompanhamento localmente no navegador.

## Primeira execução

1. Coloque o código-fonte da aplicação em `projeto/` (não coloque o próprio harness nessa pasta).
2. Edite `spec/spec.yaml` para descrever o projeto real. O arquivo inicial está vazio intencionalmente para não apresentar dados de demonstração como se fossem dados reais. A sincronização sempre reprocessa o manifesto atual, em vez de confiar num `status.json` antigo.
3. A stack é inferida a partir de arquivos no diretório `projeto/`, como `pom.xml`, `build.gradle`, `package.json`, `requirements.txt`, `*.csproj`, `go.mod` e arquivos de configuração de banco.
4. Execute `python harness.py validar` para validar a especificação.
5. Execute `iniciar_dashboard.bat` no Windows. O programa abrirá o navegador no endereço correto e exibirá o endereço no terminal. Se a porta 8765 já estiver ocupada por uma execução anterior, ele escolherá outra porta livre.
6. Clique em **Sincronizar** depois de alterar o código ou as especificações.

## Dados de demonstração

A especificação de exemplo `exemplos/spec-quadro-equipe.yaml` está separada e não é carregada pelo dashboard por padrão. Não a inclua em `harness.json` a menos que queira visualizar deliberadamente o exemplo.

## Stack automática

A detecção é heurística e usa evidências dos arquivos presentes em `projeto/`. Ela identifica tecnologias prováveis, mas não confirma que serviços estejam instalados, iniciados ou conectados. Se `projeto/` estiver vazio, o dashboard deve exibir “Nenhuma tecnologia identificada”.

## Execução

Requer Python 3.9+ e PyYAML para leitura dos arquivos YAML. Inicie a partir desta pasta para manter a configuração e os caminhos relativos corretos.
