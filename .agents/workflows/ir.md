---
description: Escolhe uma task (ex.: /ir ID_DA_TASK) e avisa de pendências anteriores
---
1. Pegue o ID da task na mensagem do usuário. Se não houver, rode `python3 harness.py proxima` e pergunte qual ele quer.
2. Rode `python3 harness.py go <ID_DA_TASK> --sem-perguntar`.
3. Se houver pendências anteriores, pergunte no chat: (1) fazer a anterior primeiro, (2) atualizar a análise para ver se alguém já fez, (3) seguir mesmo assim. Espere a resposta.
4. Na opção 2, rode `python3 harness.py status` e `go` novamente. Siga a skill `sddtrack`.
