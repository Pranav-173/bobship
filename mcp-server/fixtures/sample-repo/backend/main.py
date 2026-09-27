from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/payments")
def create_payment():
    return {"id": "pay_1"}
