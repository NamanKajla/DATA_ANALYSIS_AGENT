import os
import shutil
import httpx
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .database import db_service
from .profiler import profile_data
from .orchestrator import process_query

app = FastAPI(title="Autonomous Data Analysis Agent API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../temp_datasets"))
os.makedirs(TEMP_DATA_DIR, exist_ok=True)

class SessionCreate(BaseModel):
    title: str

class QueryRequest(BaseModel):
    question: str

class DBConnectRequest(BaseModel):
    connection_string: str
    table_name: str

def get_local_dataset_path(session_id: str, file_name: str) -> str:
    """Helper to determine the local cached path for a session's dataset."""
    ext = os.path.splitext(file_name)[-1]
    return os.path.join(TEMP_DATA_DIR, f"{session_id}_dataset{ext}")

def download_dataset_if_missing(s3_path: str, local_path: str):
    """Downloads dataset from Supabase Storage if local cache is missing."""
    if os.path.exists(local_path):
        return
        
    if not db_service.client:
        # Local mock mode fallback: copy file directly from local storage path to avoid self-request deadlock
        local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../local_storage/datasets"))
        src_path = os.path.join(local_storage_dir, s3_path)
        if os.path.exists(src_path):
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            shutil.copy(src_path, local_path)
            return
        else:
            raise HTTPException(status_code=404, detail="Dataset file not found in local storage.")
        
    # Generate signed URL
    signed_url = db_service.generate_signed_url("datasets", s3_path)
    if not signed_url:
        raise HTTPException(status_code=404, detail="Dataset file not found in storage.")
        
    # Stream download
    with httpx.Client() as client:
        response = client.get(signed_url)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch dataset from storage.")
        with open(local_path, "wb") as f:
            f.write(response.content)

@app.post("/api/sessions")
async def create_session(data: SessionCreate):
    try:
        return db_service.create_session(data.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def get_sessions():
    try:
        return db_service.get_sessions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/sessions/{session_id}")
async def rename_session(session_id: str, data: SessionCreate):
    try:
        return db_service.rename_session(session_id, data.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        # Delete local cached files
        for f in os.listdir(TEMP_DATA_DIR):
            if f.startswith(session_id):
                try:
                    os.remove(os.path.join(TEMP_DATA_DIR, f))
                except Exception:
                    pass
        db_service.delete_session(session_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/upload")
async def upload_dataset(session_id: str, file: UploadFile = File(...)):
    # 1. Validate file extension
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in [".csv", ".json", ".xls", ".xlsx"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV, JSON, or Excel.")
        
    # 2. Save file locally for profiling
    local_path = get_local_dataset_path(session_id, file.filename)
    try:
        with open(local_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write local cache: {e}")

    # 3. Profile data using DuckDB
    try:
        profile = profile_data(local_path)
    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=400, detail=f"Failed to profile dataset: {e}")

    # 4. Upload raw file to Supabase Storage
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        storage_path = f"{session_id}/dataset{ext}"
        db_service.upload_file("datasets", storage_path, file_bytes, file.content_type or "application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

    # 5. Save dataset metadata in Postgres
    try:
        dataset = db_service.create_dataset(session_id, file.filename, storage_path, profile)
        return {
            "dataset": dataset,
            "profile": profile
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {e}")

@app.get("/api/sessions/{session_id}/dataset")
async def get_session_dataset(session_id: str):
    try:
        dataset = db_service.get_dataset_by_session(session_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="No dataset uploaded for this session.")
        return dataset
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    try:
        return db_service.get_messages(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/query")
async def query_session(session_id: str, request: QueryRequest):
    # 1. Fetch dataset metadata
    dataset = db_service.get_dataset_by_session(session_id)
    if not dataset:
        raise HTTPException(status_code=400, detail="No dataset uploaded in this session. Please upload one first.")

    file_name = dataset.get("file_name")
    s3_path = dataset.get("s3_path")
    schema = dataset.get("schema_json")

    # 2. Ensure dataset is cached locally
    local_path = get_local_dataset_path(session_id, file_name)
    try:
        download_dataset_if_missing(s3_path, local_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error syncing dataset cache: {e}")

    # 3. Process query through pipeline and Sisyphus execution sandbox
    try:
        response = process_query(session_id, request.question, schema, local_path)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline Orchestration Error: {e}")

from fastapi.responses import FileResponse

@app.get("/api/sessions/{bucket_name}/files/{session_id}/{filename}")
async def get_local_storage_file(bucket_name: str, session_id: str, filename: str):
    local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../local_storage/{bucket_name}"))
    file_path = os.path.join(local_storage_dir, session_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found in local storage.")
    return FileResponse(file_path)

@app.post("/api/sessions/{session_id}/connect-db")
async def connect_sql_db(session_id: str, request: DBConnectRequest):
    from sqlalchemy import create_engine
    # 1. Ingest table using SQLAlchemy
    try:
        engine = create_engine(request.connection_string)
        with engine.connect() as con:
            # Query the table
            query = f'SELECT * FROM "{request.table_name}"'
            df = pd.read_sql_query(query, con)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database Connection Error: {e}")
    
    if df.empty:
        raise HTTPException(status_code=400, detail="The requested table has no data rows.")

    # 2. Save the pulled data as a local CSV
    file_name = f"{request.table_name}.csv"
    local_path = get_local_dataset_path(session_id, file_name)
    try:
        df.to_csv(local_path, index=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cache database table: {e}")
        
    # 3. Profile dataset using DuckDB
    try:
        profile = profile_data(local_path)
    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=400, detail=f"Failed to profile SQL table: {e}")

    # 4. Upload raw file to Storage
    storage_path = f"{session_id}/dataset.csv"
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        db_service.upload_file("datasets", storage_path, file_bytes, "text/csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

    # 5. Save dataset metadata in Database
    try:
        dataset = db_service.create_dataset(session_id, file_name, storage_path, profile)
        return {
            "dataset": dataset,
            "profile": profile
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {e}")
