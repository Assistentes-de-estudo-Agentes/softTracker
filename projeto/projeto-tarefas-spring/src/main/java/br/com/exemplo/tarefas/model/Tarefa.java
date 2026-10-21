package br.com.exemplo.tarefas.model;

import jakarta.validation.constraints.NotBlank;

public class Tarefa {
    private Long id;

    @NotBlank(message = "O título é obrigatório.")
    private String titulo;

    private String descricao;
    private boolean concluida;

    public Tarefa() {
    }

    public Tarefa(Long id, String titulo, String descricao, boolean concluida) {
        this.id = id;
        this.titulo = titulo;
        this.descricao = descricao;
        this.concluida = concluida;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTitulo() {
        return titulo;
    }

    public void setTitulo(String titulo) {
        this.titulo = titulo;
    }

    public String getDescricao() {
        return descricao;
    }

    public void setDescricao(String descricao) {
        this.descricao = descricao;
    }

    public boolean isConcluida() {
        return concluida;
    }

    public void setConcluida(boolean concluida) {
        this.concluida = concluida;
    }
}
