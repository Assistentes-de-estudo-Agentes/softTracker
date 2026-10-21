package br.com.exemplo.tarefas.controller;

import br.com.exemplo.tarefas.model.Tarefa;
import br.com.exemplo.tarefas.service.TarefaService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/tarefas")
public class TarefaController {
    private final TarefaService tarefaService;

    public TarefaController(TarefaService tarefaService) {
        this.tarefaService = tarefaService;
    }

    @GetMapping
    public List<Tarefa> listarTodas() {
        return tarefaService.listarTodas();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Tarefa criar(@Valid @RequestBody Tarefa tarefa) {
        return tarefaService.criar(tarefa);
    }

    // TODO: GET /tarefas/{id} — consultar uma tarefa específica.
    // TODO: PUT /tarefas/{id} — atualizar uma tarefa.
    // TODO: DELETE /tarefas/{id} — remover uma tarefa.
}
