# sddtrack — regras fixas
- A pasta `projeto/` é o código do produto e só é lida pelo harness. Não a modifique sem pedido explícito do usuário.
- A pasta `estado/` é gerada pelo `harness.py`; nunca a edite manualmente.
- Perguntas sobre progresso, "o que falta" ou "qual a próxima task" devem ser respondidas rodando `harness.py status`/`proxima` (skill `sddtrack`), nunca de memória.
- Código presente em `projeto/` já foi revisado: não rode testes nem valide qualidade ao avaliar tasks.
