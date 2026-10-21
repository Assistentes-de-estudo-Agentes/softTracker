@app.post("/cards")
def criar_cartao(dados):
    if not dados.get("titulo"):
        raise ValueError("título obrigatório")
    return dados
