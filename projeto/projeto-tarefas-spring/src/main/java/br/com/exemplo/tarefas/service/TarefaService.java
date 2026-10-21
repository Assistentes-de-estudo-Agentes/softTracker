package br.com.exemplo.tarefas.service;

import br.com.exemplo.tarefas.model.Tarefa;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class TarefaService {
    private final List<Tarefa> tarefas = new ArrayList<>();
    private long proximoId = 1;

    public List<Tarefa> listarTodas() {
        return new ArrayList<>(tarefas);
    }

    public Tarefa criar(Tarefa tarefa) {
        tarefa.setId(proximoId++);
        tarefa.setConcluida(false);
        tarefas.add(tarefa);
        return tarefa;
    }

    // TODO: implementar busca de tarefa por ID.
    // TODO: implementar atualização de tarefa.
    // TODO: implementar remoção de tarefa.
}
