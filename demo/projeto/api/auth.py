@app.post("/login")
def login():
    return "ok"

@app.post("/register")
def register():
    return "ok"

def comparar_hash_senha(a, b):
    return a == b
