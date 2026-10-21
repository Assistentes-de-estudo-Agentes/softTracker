# Gerenciador simples de tarefas

Projeto didático de API REST com Java 17 e Spring Boot. A especificação funcional fica em `spec/especificacao.yml`, separada do código.

## O que já funciona

- `POST /tarefas` — cadastra uma tarefa.
- `GET /tarefas` — lista as tarefas cadastradas.
- Validação de título obrigatório.

## O que está especificado, mas ainda não foi implementado

- `GET /tarefas/{id}` — consultar por identificador.
- `PUT /tarefas/{id}` — atualizar uma tarefa.
- `DELETE /tarefas/{id}` — excluir uma tarefa.

Esses casos de uso estão no YAML como `nao_implementado` e possuem comentários `TODO` no código.

## Como executar

É necessário ter Java 17+ e Maven instalado. Na raiz do projeto, execute:

```bash
mvn spring-boot:run
```

A API inicia em `http://localhost:8080`.

## Testar os endpoints

Cadastrar:

```bash
curl -X POST http://localhost:8080/tarefas \
  -H "Content-Type: application/json" \
  -d '{"titulo":"Estudar Spring","descricao":"Criar minha primeira API"}'
```

Listar:

```bash
curl http://localhost:8080/tarefas
```

## Estrutura

```text
projeto-tarefas/
├── spec/
│   └── especificacao.yml
├── src/main/java/br/com/exemplo/tarefas/
│   ├── TarefaApplication.java
│   ├── controller/TarefaController.java
│   ├── model/Tarefa.java
│   └── service/TarefaService.java
├── src/main/resources/application.yml
├── pom.xml
└── README.md
```

## Observações

- Os dados são mantidos apenas na memória e desaparecem ao reiniciar a aplicação.
- `spec/especificacao.yml` descreve objetivo, stack, requisitos funcionais e não funcionais, casos de uso, critérios de aceitação e tarefas de desenvolvimento.
- O YAML é uma especificação do projeto; ele não implementa automaticamente os casos de uso.
