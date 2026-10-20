---
description: Mostra o progresso do projeto (o que foi feito e o que falta)
---
1. Rode `python3 harness.py status` na raiz do workspace.
2. Se houver critérios aguardando julgamento, siga o fluxo "julgar pendências" da skill `sddtrack` e rode `status --resumo` de novo.
3. Resuma: progresso das tasks e dos critérios, o que mudou, próximas tasks liberadas (`python3 harness.py proxima`) e avisos.
