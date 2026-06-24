from fastapi import FastApi

    
app = FastApi()

@app.get("/health")
def health():
    return {"response": "ok"}