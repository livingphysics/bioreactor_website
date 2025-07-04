from fastapi import FastAPI, Request, Form, UploadFile, File, status, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from pathlib import Path
import httpx
import io
import uuid
import json

# App setup
app = FastAPI(title="Bioreactor Web Server", description="User interface for bioreactor experiments.")

# Static and template directories
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads_tmp"
UPLOADS_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Hub API config (could be loaded from env)
HUB_API_URL = os.getenv("BIOREACTOR_HUB_API_URL", "http://localhost:8000")

# Simple session storage (in production, use proper session management)
user_sessions = {}

def get_or_create_session_id(request: Request) -> str:
    """Get or create a session ID for the user"""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in user_sessions:
        session_id = str(uuid.uuid4())
        user_sessions[session_id] = {"created_at": "now"}
    return session_id

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    session_id = get_or_create_session_id(request)
    response = templates.TemplateResponse("home.html", {"request": request})
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response

@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    session_id = get_or_create_session_id(request)
    response = templates.TemplateResponse("upload.html", {"request": request})
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response

@app.post("/upload", response_class=HTMLResponse)
async def upload_script(request: Request, file: UploadFile = File(...)):
    session_id = get_or_create_session_id(request)
    
    # Validate file extension
    if not file.filename.endswith(".py"):
        return templates.TemplateResponse(
            "upload.html", {"request": request, "error": "Only .py files are allowed."}
        )
    
    # Save file to uploads_tmp
    file_location = UPLOADS_DIR / file.filename
    content = await file.read()
    with open(file_location, "wb") as f:
        f.write(content)
    
    # Submit to hub with session ID
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{HUB_API_URL}/api/experiments/start",
                json={"script_content": content.decode("utf-8")},
                headers={"X-Session-ID": session_id}
            )
        
        if resp.status_code == 200:
            data = resp.json()
            experiment_id = data.get("experiment_id")
            queue_position = data.get("queue_position")
            
            return templates.TemplateResponse(
                "upload.html", {
                    "request": request,
                    "success": f"Uploaded and queued {file.filename} successfully.",
                    "experiment_id": experiment_id,
                    "queue_position": queue_position
                }
            )
        else:
            return templates.TemplateResponse(
                "upload.html", {"request": request, "error": f"Hub error: {resp.text}"}
            )
    except Exception as e:
        return templates.TemplateResponse(
            "upload.html", {"request": request, "error": f"Failed to submit to hub: {e}"}
        )

@app.get("/queue", response_class=HTMLResponse)
async def queue_status(request: Request):
    """Show queue status and admin controls"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{HUB_API_URL}/api/queue/status")
        
        if resp.status_code == 200:
            queue_data = resp.json()
            return templates.TemplateResponse(
                "queue_status.html", {"request": request, "queue": queue_data}
            )
        else:
            return templates.TemplateResponse(
                "queue_status.html", {"request": request, "error": f"Hub error: {resp.text}"}
            )
    except Exception as e:
        return templates.TemplateResponse(
            "queue_status.html", {"request": request, "error": f"Failed to get queue status: {e}"}
        )

@app.get("/experiment/{experiment_id}", response_class=HTMLResponse)
async def experiment_status(request: Request, experiment_id: str):
    session_id = get_or_create_session_id(request)
    
    # Query hub for experiment status
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{HUB_API_URL}/api/experiments/{experiment_id}/status")
        
        if resp.status_code == 200:
            data = resp.json()
            experiment = data.get("experiment", {})
            
            # Get queue status for wait time estimation
            queue_resp = await client.get(f"{HUB_API_URL}/api/queue/status")
            queue_data = queue_resp.json() if queue_resp.status_code == 200 else {}
            
            return templates.TemplateResponse(
                "experiment_status.html", {
                    "request": request, 
                    "experiment": experiment, 
                    "experiment_id": experiment_id,
                    "queue_data": queue_data
                }
            )
        else:
            return templates.TemplateResponse(
                "experiment_status.html", {"request": request, "error": f"Hub error: {resp.text}", "experiment_id": experiment_id}
            )
    except Exception as e:
        return templates.TemplateResponse(
            "experiment_status.html", {"request": request, "error": f"Failed to contact hub: {e}", "experiment_id": experiment_id}
        )

@app.get("/my-experiments", response_class=HTMLResponse)
async def my_experiments(request: Request):
    """Show user's experiments"""
    session_id = get_or_create_session_id(request)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{HUB_API_URL}/api/experiments/user",
                headers={"X-Session-ID": session_id}
            )
        
        if resp.status_code == 200:
            data = resp.json()
            experiments = data.get("experiments", [])
            return templates.TemplateResponse(
                "my_experiments.html", {"request": request, "experiments": experiments}
            )
        else:
            return templates.TemplateResponse(
                "my_experiments.html", {"request": request, "error": f"Hub error: {resp.text}"}
            )
    except Exception as e:
        return templates.TemplateResponse(
            "my_experiments.html", {"request": request, "error": f"Failed to get experiments: {e}"}
        )

# Admin control endpoints
@app.post("/api/experiments/{experiment_id}/cancel")
async def cancel_experiment_api(experiment_id: str):
    """Cancel an experiment"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{HUB_API_URL}/api/experiments/{experiment_id}/cancel")
        
        if resp.status_code == 200:
            return {"success": True, "message": "Experiment cancelled successfully"}
        else:
            return {"success": False, "message": f"Failed to cancel: {resp.text}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.post("/api/experiments/{experiment_id}/pause")
async def pause_experiment_api(experiment_id: str):
    """Pause an experiment"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{HUB_API_URL}/api/experiments/{experiment_id}/pause")
        
        if resp.status_code == 200:
            return {"success": True, "message": "Experiment paused successfully"}
        else:
            return {"success": False, "message": f"Failed to pause: {resp.text}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.post("/api/experiments/{experiment_id}/resume")
async def resume_experiment_api(experiment_id: str):
    """Resume an experiment"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{HUB_API_URL}/api/experiments/{experiment_id}/resume")
        
        if resp.status_code == 200:
            return {"success": True, "message": "Experiment resumed successfully"}
        else:
            return {"success": False, "message": f"Failed to resume: {resp.text}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.post("/api/experiments/{experiment_id}/reorder")
async def reorder_experiment_api(experiment_id: str, new_position: int):
    """Reorder an experiment"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{HUB_API_URL}/api/experiments/{experiment_id}/reorder?new_position={new_position}")
        
        if resp.status_code == 200:
            return {"success": True, "message": "Experiment reordered successfully"}
        else:
            return {"success": False, "message": f"Failed to reorder: {resp.text}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {e}"}

@app.get("/experiment/{experiment_id}/download")
async def download_experiment_results(experiment_id: str):
    # Proxy the download from the hub
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{HUB_API_URL}/api/experiments/{experiment_id}/download")
        if resp.status_code == 200:
            return StreamingResponse(io.BytesIO(resp.content),
                                     media_type="application/zip",
                                     headers={
                                         "Content-Disposition": f"attachment; filename=experiment_{experiment_id}_results.zip"
                                     })
        else:
            raise HTTPException(status_code=resp.status_code, detail=f"Hub error: {resp.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download results: {e}") 
