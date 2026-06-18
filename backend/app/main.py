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

@app.delete("/api/sessions/{session_id}/messages")
async def clear_session_messages(session_id: str):
    try:
        if not db_service.client:
            db_service.mock_messages[session_id] = []
        else:
            db_service.client.table("messages").delete().eq("session_id", session_id).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}/dataset")
async def delete_session_dataset(session_id: str):
    try:
        if not db_service.client:
            db_service.mock_datasets.pop(session_id, None)
            db_service.mock_messages[session_id] = []
        else:
            db_service.client.table("datasets").delete().eq("session_id", session_id).execute()
            db_service.client.table("messages").delete().eq("session_id", session_id).execute()
        
        # Also delete local cached files
        for f in os.listdir(TEMP_DATA_DIR):
            if f.startswith(session_id):
                try:
                    os.remove(os.path.join(TEMP_DATA_DIR, f))
                except Exception:
                    pass
                    
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/upload")
async def upload_dataset(session_id: str, file: UploadFile = File(...)):
    # 1. Validate file extension
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in [".csv", ".json", ".xls", ".xlsx"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV, JSON, or Excel.")

    # 2. Read file into memory first so we can check size before touching disk
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}")

    # 3. Enforce maximum file size
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {max_mb} MB. "
                   f"Your file is {len(file_bytes) // (1024 * 1024)} MB."
        )

    # 4. Write to local cache
    local_path = get_local_dataset_path(session_id, file.filename)
    try:
        with open(local_path, "wb") as buffer:
            buffer.write(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write local cache: {e}")

    # 5. Profile data using DuckDB
    try:
        profile = profile_data(local_path)
    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=400, detail=f"Failed to profile dataset: {e}")

    # 6. Upload raw file to Supabase Storage
    base_id = session_id.split(":")[0]
    try:
        storage_path = f"{base_id}/dataset{ext}"
        db_service.upload_file("datasets", storage_path, file_bytes, file.content_type or "application/octet-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {e}")

    # 7. Save dataset metadata in Postgres
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
@app.get("/api/sessions/{session_id}/dataset/preview")
async def get_dataset_preview(session_id: str):
    try:
        dataset = db_service.get_dataset_by_session(session_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="No dataset uploaded for this session.")
        
        file_name = dataset.get("file_name")
        s3_path = dataset.get("s3_path")
        local_path = get_local_dataset_path(session_id, file_name)
        
        download_dataset_if_missing(s3_path, local_path)
        
        ext = os.path.splitext(local_path)[-1].lower()
        if ext == ".csv":
            df = pd.read_csv(local_path, nrows=15)
        elif ext == ".json":
            df = pd.read_json(local_path)
            df = df.head(15)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(local_path, nrows=15)
        else:
            raise HTTPException(status_code=400, detail="Unsupported dataset format.")
            
        # Convert NaN/Infinity values to None for JSON compliance
        df = df.replace({pd.NA: None})
        df = df.where(pd.notnull(df), None)
        
        return {
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/sessions/{session_id}/dataset/view")
async def get_dataset_view(session_id: str):
    from fastapi.responses import HTMLResponse
    try:
        dataset = db_service.get_dataset_by_session(session_id)
        if not dataset:
            return HTMLResponse("<h3>No dataset uploaded for this session.</h3>", status_code=404)
        
        file_name = dataset.get("file_name")
        s3_path = dataset.get("s3_path")
        local_path = get_local_dataset_path(session_id, file_name)
        
        download_dataset_if_missing(s3_path, local_path)
        
        ext = os.path.splitext(local_path)[-1].lower()
        if ext == ".csv":
            df = pd.read_csv(local_path, nrows=100)
        elif ext == ".json":
            df = pd.read_json(local_path).head(100)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(local_path, nrows=100)
        else:
            return HTMLResponse("<h3>Unsupported file format.</h3>", status_code=400)
            
        html_table = df.to_html(classes="table-preview", index=False, na_rep="null")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dataset View - {file_name}</title>
            <style>
                body {{
                    background-color: #09090b;
                    color: #e4e4e7;
                    font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    padding: 24px;
                    margin: 0;
                }}
                .header {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 20px;
                    border-bottom: 1px solid #27272a;
                    padding-bottom: 12px;
                }}
                h1 {{
                    font-size: 1.25rem;
                    margin: 0;
                    font-weight: 600;
                    color: #ffffff;
                }}
                .subtitle {{
                    font-size: 0.8rem;
                    color: #a1a1aa;
                }}
                .table-container {{
                    overflow-x: auto;
                    border: 1px solid #27272a;
                    border-radius: 8px;
                    background-color: #121214;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 0.85rem;
                    text-align: left;
                    font-family: monospace;
                }}
                th {{
                    background-color: #18181b;
                    color: #d4d4d8;
                    padding: 10px 12px;
                    font-weight: 600;
                    border-bottom: 1px solid #27272a;
                    border-right: 1px solid #27272a;
                }}
                td {{
                    padding: 8px 12px;
                    border-bottom: 1px solid #27272a;
                    border-right: 1px solid #27272a;
                    color: #a1a1aa;
                    max-width: 250px;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }}
                tr:hover {{
                    background-color: #1c1c1f;
                }}
                tr:nth-child(even) {{
                    background-color: #141417;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1>{file_name}</h1>
                    <div class="subtitle">Showing first 100 rows &bull; Total rows: {dataset.get("schema_json", {}).get("total_rows", "unknown")}</div>
                </div>
            </div>
            <div class="table-container">
                {html_table}
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        return HTMLResponse(f"<h3>Error rendering preview: {str(e)}</h3>", status_code=500)

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
