"""FastAPI app — serves the UI and API endpoints."""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipeline import run_pipeline
from agents import agent_chat

app = FastAPI(title="ScriptScope", description="Multi-agent script analysis engine")

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Load sample scripts
SAMPLES: dict[str, str] = {}
samples_dir = BASE_DIR / "sample_scripts"
if samples_dir.exists():
    for f in samples_dir.glob("*.txt"):
        SAMPLES[f.stem.replace("_", " ").title()] = f.read_text()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "samples": SAMPLES,
    })


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, script: str = Form(...)):
    try:
        result = await run_pipeline(script)
        result_dict = result.model_dump()
        return templates.TemplateResponse("results.html", {
            "request": request,
            "result": result_dict,
            "result_json": json.dumps(result_dict, indent=2, default=str),
            "script": script,
        })
    except Exception as e:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "samples": SAMPLES,
            "error": str(e),
        })


@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    agent_name = data.get("agent", "Story Analyst")
    message = data.get("message", "")
    analysis = data.get("analysis", {})

    response = await asyncio.to_thread(agent_chat, agent_name, message, analysis)
    return JSONResponse({"response": response})


@app.get("/architecture", response_class=HTMLResponse)
async def architecture(request: Request):
    return templates.TemplateResponse("architecture.html", {"request": request})


@app.get("/api/samples")
async def get_samples():
    return JSONResponse(SAMPLES)


@app.get("/health")
async def health():
    return {"status": "ok"}
