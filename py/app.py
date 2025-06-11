import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
packages_path = os.path.join(current_dir, 'python_packages')
sys.path.insert(0, packages_path)

import json
import base64
import requests
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Template and static files setup
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Get data directory
DATA_DIR = os.environ.get('LYNK_DATA_DIR')
print(f"Data Directory 1app.py-->: {DATA_DIR}")


def ensure_data_directory():
    """Ensure the data directory exists"""
    try:
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Failed to create data directory: {e}")
        raise


def get_data_file_path(filename):
    print(f"Getting data file path for {filename}")
    print(f"Data Directory app.py -->: {DATA_DIR}")
    return os.path.join(DATA_DIR, filename)


def load_time_data():
    try:
        time_file = get_data_file_path("time.json")
        if os.path.exists(time_file):
            with open(time_file, "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading time data: {e}")
        return {}


def image_url_to_base64(image_url: str) -> str:
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch image from URL")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Image fetch error: {e}")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/tracking", response_class=HTMLResponse)
async def tracking_get(request: Request):
    try:
        apps_path = get_data_file_path("apps.json")
        apps_data = {}
        if os.path.isfile(apps_path):
            with open(apps_path, "r") as f:
                apps_data = json.load(f)
                print(f"Loaded apps data: {apps_data}")
        else:
            print(f"No apps.json found at {apps_path}")
        return templates.TemplateResponse("tracking.html", {"request": request, "apps_data": apps_data})
    except Exception as e:
        print(f"Error loading apps data: {e}")
        return templates.TemplateResponse("tracking.html", {"request": request, "apps_data": {}}  )


@app.post("/tracking")
async def tracking_post(apps_data: dict):
    try:
        ensure_data_directory()
        apps_path = get_data_file_path("apps.json")
        with open(apps_path, "w") as f:
            json.dump(apps_data, f, indent=4)
        return {"message": "apps.json updated successfully"}
    except Exception as e:
        print(f"Error saving apps data: {e}")
        raise HTTPException(status_code=500, detail="Failed to update apps data")


@app.get("/api/hello")
def hello():
    return {"message": "Hello from FastAPI!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/connection", response_class=HTMLResponse)
async def get_connection(request: Request):
    connection_path = get_data_file_path("connection.json")
    try:
        if os.path.exists(connection_path):
            with open(connection_path, "r") as file:
                data = json.load(file)
        else:
            data = {
                "websocket_url": "https://lynk-ws-server.onrender.com",
                "connection_id": "default"
            }
        return templates.TemplateResponse("connection.html", {"request": request, "data": data})
    except Exception as e:
        print(f"Error loading connection data: {e}")
        return templates.TemplateResponse("connection.html", {"request": request, "data": {}})


class UpdateAppRequest(BaseModel):
    app_name: str
    alias: str
    icon_url: str = None


@app.post("/api/update-app")
async def api_update_alias(data: UpdateAppRequest):
    try:
        apps_path = get_data_file_path("apps.json")
        if not os.path.isfile(apps_path):
            raise HTTPException(status_code=404, detail="apps.json not found")

        with open(apps_path, "r") as f:
            apps_data = json.load(f)

        if data.app_name not in apps_data:
            raise HTTPException(status_code=404, detail=f"App '{data.app_name}' not found")

        if data.icon_url:
            try:
                icon_base64 = image_url_to_base64(data.icon_url)
                apps_data[data.app_name]["icon"] = icon_base64
                apps_data[data.app_name]["icon_url"] = data.icon_url
            except HTTPException as e:
                raise e

        apps_data[data.app_name]["alias"] = data.alias

        with open(apps_path, "w") as f:
            json.dump(apps_data, f, indent=4)

        return {"message": "success"}
    except Exception as e:
        print(f"Error updating app: {e}")
        raise HTTPException(status_code=500, detail="Failed to update app")


class UpdateConnectionRequest(BaseModel):
    websocket_url: str
    connection_id: str


@app.post("/update-connection")
async def update_connection(data: UpdateConnectionRequest):
    try:
        ensure_data_directory()
        connection_path = get_data_file_path("connection.json")

        if os.path.exists(connection_path):
            with open(connection_path, "r") as f:
                existing_data = json.load(f)
        else:
            existing_data = {}

        existing_data["websocket_url"] = data.websocket_url
        existing_data["connection_id"] = data.connection_id

        with open(connection_path, "w") as f:
            json.dump(existing_data, f, indent=2)

        return {"message": "connection.json updated", "data": existing_data}
    except Exception as e:
        print(f"Error updating connection: {e}")
        raise HTTPException(status_code=500, detail="Failed to update connection")


if __name__ == "__main__":
    ensure_data_directory()
    print("Starting FastAPI server at http://127.0.0.1:5001")
    uvicorn.run("app:app", host="127.0.0.1", port=5001, reload=True)
