
import argparse
import asyncio
import json
from xmlrpc import client
import requests
import openai

def print_json_or_text(response):
    try:
        data = response.json()
        print(data)
        return data
    except ValueError:
        # Fallback when endpoint returns plain text or invalid JSON.
        print("Respuesta no JSON:", response.text)
        return None


async def say_async_hello():
    print("Hello, Asyncio!")


def run_client():
    asyncio.run(say_async_hello())
    try:
        result = 10 / 0
        print(result)
    except Exception as e:
        print(e)

    data = None

    try:
        response = requests.get("http://localhost:8080/health", timeout=10)
        data = print_json_or_text(response)
    except requests.RequestException as e:
        print(f"Error en GET /health: {e}")

    payload = {"id": "evt", "type": "test", "payload": "x"}
    try:
        response = requests.post("http://localhost:8080/events", json=payload, timeout=10)
        data = print_json_or_text(response)
    except requests.RequestException as e:
        print(f"Error en POST /events: {e}")

    if data is not None:
        print(json.dumps(data))

    asyncio.run(say_async_hello())

    from openai import OpenAI

    client = OpenAI()

    prompt = """
    Extract the name and email from this text:
    John Doe - john@email.com
    """
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    print(response.output_text)


def run_server():
    import uvicorn

    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/")
    def read_root():
        return {"Hello": "World"}

    @app.get("/items/{item_id}")
    
    def read_item(item_id: int, q: str = None):
        return {"item_id": item_id, "q": q}
    
    uvicorn.run(app, host="127.0.0.1", port=8081)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ejecuta cliente o servidor FastAPI")
    parser.add_argument(
        "--mode",
        choices=["client", "server"],
        default="server",
        help="Modo de ejecucion: client para requests, server para FastAPI",
    )
    args = parser.parse_args()

    if args.mode == "client":
        run_client()
    else:
        run_server()


