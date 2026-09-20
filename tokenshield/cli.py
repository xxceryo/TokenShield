import uvicorn


def main():
    uvicorn.run("tokenshield.server:app", host="127.0.0.1", port=8787, reload=False)
