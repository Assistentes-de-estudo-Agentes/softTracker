class User:
    def __init__(self, email, senha_hash):
        self.email = email
        self.senha_hash = senha_hash


class Board:
    def __init__(self, nome, dono):
        self.nome = nome
        self.dono = dono


class Card:
    def __init__(self, titulo, quadro):
        self.titulo = titulo
        self.quadro = quadro
