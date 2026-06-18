import os
import shutil
import httpx
import pandas as pd
import re
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header
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

@app.get("/health")
async def health_check():
    """Lightweight ping endpoint to keep the HF Space warm."""
    return {"status": "ok"}

class SessionCreate(BaseModel):
    title: str

class QueryRequest(BaseModel):
    question: str
    chart_url: Optional[str] = None

class DBConnectRequest(BaseModel):
    connection_string: str
    table_name: str

def get_local_dataset_path(session_id: str, file_name: str) -> str:
    """Helper to determine the local cached path for a session's dataset."""
    base_id = session_id.split(":")[0]
    ext = os.path.splitext(file_name)[-1]
    return os.path.join(TEMP_DATA_DIR, f"{base_id}_dataset{ext}")

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

def get_demo_titanic_csv() -> bytes:
    import io
    data = [
        {"PassengerId": 1, "Survived": 0, "Pclass": 3, "Name": "Braund, Mr. Owen Harris", "Sex": "male", "Age": 22, "SibSp": 1, "Parch": 0, "Ticket": "A/5 21171", "Fare": 7.25, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 2, "Survived": 1, "Pclass": 1, "Name": "Cumings, Mrs. John Bradley (Florence Briggs Thayer)", "Sex": "female", "Age": 38, "SibSp": 1, "Parch": 0, "Ticket": "PC 17599", "Fare": 71.2833, "Cabin": "C85", "Embarked": "C"},
        {"PassengerId": 3, "Survived": 1, "Pclass": 3, "Name": "Heikkinen, Miss. Laina", "Sex": "female", "Age": 26, "SibSp": 0, "Parch": 0, "Ticket": "STON/O2. 3101282", "Fare": 7.925, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 4, "Survived": 1, "Pclass": 1, "Name": "Futrelle, Mrs. Jacques Heath (Lily May Peel)", "Sex": "female", "Age": 35, "SibSp": 1, "Parch": 0, "Ticket": "113803", "Fare": 53.1, "Cabin": "C123", "Embarked": "S"},
        {"PassengerId": 5, "Survived": 0, "Pclass": 3, "Name": "Allen, Mr. William Henry", "Sex": "male", "Age": 35, "SibSp": 0, "Parch": 0, "Ticket": "373450", "Fare": 8.05, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 6, "Survived": 0, "Pclass": 3, "Name": "Moran, Mr. James", "Sex": "male", "Age": None, "SibSp": 0, "Parch": 0, "Ticket": "330877", "Fare": 8.4583, "Cabin": None, "Embarked": "Q"},
        {"PassengerId": 7, "Survived": 0, "Pclass": 1, "Name": "McCarthy, Mr. Timothy J", "Sex": "male", "Age": 54, "SibSp": 0, "Parch": 0, "Ticket": "17463", "Fare": 51.8625, "Cabin": "E46", "Embarked": "S"},
        {"PassengerId": 8, "Survived": 0, "Pclass": 3, "Name": "Palsson, Master. Gosta Leonard", "Sex": "male", "Age": 2, "SibSp": 3, "Parch": 1, "Ticket": "349909", "Fare": 21.075, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 9, "Survived": 1, "Pclass": 3, "Name": "Johnson, Mrs. Oscar W (Elisabeth Vilhelmina Berg)", "Sex": "female", "Age": 27, "SibSp": 0, "Parch": 2, "Ticket": "347742", "Fare": 11.1333, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 10, "Survived": 1, "Pclass": 2, "Name": "Nasser, Mrs. Nicholas (Adele Achem)", "Sex": "female", "Age": 14, "SibSp": 1, "Parch": 0, "Ticket": "237736", "Fare": 30.0708, "Cabin": None, "Embarked": "C"},
        {"PassengerId": 11, "Survived": 1, "Pclass": 3, "Name": "Sandstrom, Miss. Marguerite Rut", "Sex": "female", "Age": 4, "SibSp": 1, "Parch": 1, "Ticket": "PP 9549", "Fare": 16.7, "Cabin": "G6", "Embarked": "S"},
        {"PassengerId": 12, "Survived": 1, "Pclass": 1, "Name": "Bonnell, Miss. Elizabeth", "Sex": "female", "Age": 58, "SibSp": 0, "Parch": 0, "Ticket": "113783", "Fare": 26.55, "Cabin": "C103", "Embarked": "S"},
        {"PassengerId": 13, "Survived": 0, "Pclass": 3, "Name": "Saundercock, Mr. William Henry", "Sex": "male", "Age": 20, "SibSp": 0, "Parch": 0, "Ticket": "A/5. 2151", "Fare": 8.05, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 14, "Survived": 0, "Pclass": 3, "Name": "Andersson, Mr. Anders Johan", "Sex": "male", "Age": 39, "SibSp": 1, "Parch": 5, "Ticket": "347082", "Fare": 31.275, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 15, "Survived": 0, "Pclass": 3, "Name": "Vestrom, Miss. Hulda Amanda Adolfina", "Sex": "female", "Age": 14, "SibSp": 0, "Parch": 0, "Ticket": "350406", "Fare": 7.8542, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 16, "Survived": 1, "Pclass": 2, "Name": "Hewlett, Mrs. (Mary D Kingcome) ", "Sex": "female", "Age": 55, "SibSp": 0, "Parch": 0, "Ticket": "248706", "Fare": 16.0, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 17, "Survived": 0, "Pclass": 3, "Name": "Rice, Master. Eugene", "Sex": "male", "Age": 2, "SibSp": 4, "Parch": 1, "Ticket": "382652", "Fare": 29.125, "Cabin": None, "Embarked": "Q"},
        {"PassengerId": 18, "Survived": 1, "Pclass": 2, "Name": "Williams, Mr. Charles Eugene", "Sex": "male", "Age": None, "SibSp": 0, "Parch": 0, "Ticket": "244373", "Fare": 13.0, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 19, "Survived": 0, "Pclass": 3, "Name": "Vander Planke, Mrs. Julius (Emelia Maria Vandemoortele)", "Sex": "female", "Age": 31, "SibSp": 1, "Parch": 0, "Ticket": "345763", "Fare": 18.0, "Cabin": None, "Embarked": "S"},
        {"PassengerId": 20, "Survived": 1, "Pclass": 3, "Name": "Masselmani, Mrs. Fatima", "Sex": "female", "Age": None, "SibSp": 0, "Parch": 0, "Ticket": "2649", "Fare": 7.225, "Cabin": None, "Embarked": "C"}
    ]
    df = pd.DataFrame(data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    return stream.getvalue().encode('utf-8')

@app.post("/api/sessions/create-demo")
async def create_demo_session(x_device_id: Optional[str] = Header(default="default", alias="X-Device-ID")):
    device_id = x_device_id or "default"
    try:
        session = db_service.create_session("Demo Data Analysis", device_id=device_id)
        session_id = session["id"]
        
        file_bytes = get_demo_titanic_csv()
        file_name = "titanic.csv"
        
        local_path = get_local_dataset_path(session_id, file_name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
            
        profile = profile_data(local_path)
        
        storage_path = f"{session_id}/{file_name}"
        db_service.upload_file("datasets", storage_path, file_bytes, "text/csv")
        dataset = db_service.create_dataset(session_id, file_name, storage_path, profile)
        
        intro_content = (
            "Hello! I have loaded the Titanic passenger survival dataset for you.\n\n"
            "This complex dataset contains demographic details of passengers (Age, Sex, Cabin, Fare) and their survival outcome. "
            "Let's explore it! You can ask questions in natural language, clean the dataset, or try one of the suggestions below:"
        )
        db_service.save_message(
            session_id=session_id,
            role="assistant",
            content=intro_content,
            follow_ups=[
                "Compare survival rates by sex",
                "Show the average fare paid by passenger class",
                "Show age distribution of survivors"
            ]
        )
        
        return {
            "success": True,
            "session": session,
            "dataset": dataset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions")
async def create_session(data: SessionCreate, x_device_id: Optional[str] = Header(default="default", alias="X-Device-ID")):
    device_id = x_device_id or "default"
    try:
        return db_service.create_session(data.title, device_id=device_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions")
async def get_sessions(x_device_id: Optional[str] = Header(default="default", alias="X-Device-ID")):
    device_id = x_device_id or "default"
    try:
        return db_service.get_sessions(device_id=device_id)
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
        db_service.clear_messages(session_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}/dataset")
async def delete_session_dataset(session_id: str):
    base_id = session_id.split(":")[0]
    try:
        if not db_service.client:
            db_service.mock_datasets.pop(base_id, None)
            db_service.mock_messages[base_id] = []
        else:
            db_service.client.table("datasets").delete().eq("session_id", base_id).execute()
            db_service.client.table("messages").delete().eq("session_id", base_id).execute()
        
        # Also delete local cached files
        for f in os.listdir(TEMP_DATA_DIR):
            if f.startswith(base_id):
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
    if ext not in [".csv", ".json", ".xls", ".xlsx", ".sql"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV, JSON, Excel, or SQL.")

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

    # 3.5 Parse SQL file if extension is .sql
    if ext == ".sql":
        try:
            sql_text = file_bytes.decode("utf-8", errors="ignore")
            # Clean MySQL-specific dump constraints
            sql_clean = sql_text.replace(chr(96), '')
            sql_clean = re.sub(r'ENGINE\s*=\s*\w+', '', sql_clean, flags=re.IGNORECASE)
            sql_clean = re.sub(r'DEFAULT\s+CHARSET\s*=\s*\w+', '', sql_clean, flags=re.IGNORECASE)
            sql_clean = re.sub(r'AUTO_INCREMENT\s*=\s*\d+', '', sql_clean, flags=re.IGNORECASE)
            sql_clean = re.sub(r'int\(\d+\)', 'int', sql_clean, flags=re.IGNORECASE)
            sql_clean = re.sub(r'tinyint\(\d+\)', 'int', sql_clean, flags=re.IGNORECASE)
            sql_clean = re.sub(r'AUTO_INCREMENT', '', sql_clean, flags=re.IGNORECASE)

            # Execute in temporary DuckDB connection to extract the data
            # pyrefly: ignore [missing-import]
            import duckdb
            temp_con = duckdb.connect(database=':memory:')
            temp_con.execute(sql_clean)
            tables = temp_con.execute("PRAGMA show_tables").fetchall()
            if not tables:
                raise HTTPException(status_code=400, detail="No tables found in the uploaded SQL file.")
            
            # Use the first table found
            target_table = tables[0][0]
            df = temp_con.execute(f'SELECT * FROM "{target_table}"').df()
            temp_con.close()

            # Save as CSV internally
            local_path = get_local_dataset_path(session_id, f"{target_table}.csv")
            df.to_csv(local_path, index=False)
            
            # Set ext to .csv so the rest of the logic stores it as CSV
            ext = ".csv"
            file.filename = f"{target_table}.csv"
            
            # Read the generated CSV bytes to upload to Supabase
            with open(local_path, "rb") as f:
                file_bytes = f.read()

        except Exception as sql_err:
            raise HTTPException(status_code=400, detail=f"Failed to parse SQL file: {sql_err}")

    # 4. Write to local cache (skip if already generated from SQL)
    local_path = get_local_dataset_path(session_id, file.filename)
    if not os.path.exists(local_path):
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

@app.post("/api/sessions/{session_id}/clean-dataset")
async def clean_session_dataset(session_id: str):
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
            df = pd.read_csv(local_path)
        elif ext == ".json":
            df = pd.read_json(local_path)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(local_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported dataset format.")
            
        # Perform standard cleaning
        # 1. Strip string column whitespaces
        for col in df.select_dtypes(include=['object']):
            df[col] = df[col].astype(str).str.strip()
            
        # 2. Fill missing numerical values with 0
        for col in df.select_dtypes(include=['number']):
            if df[col].isnull().any():
                df[col] = df[col].fillna(0)
                
        # 3. Drop columns that are completely null
        df = df.dropna(how='all', axis=1)
        
        # Save back to local path
        if ext == ".csv":
            df.to_csv(local_path, index=False)
        elif ext == ".json":
            df.to_json(local_path, orient="records")
        elif ext in [".xls", ".xlsx"]:
            df.to_excel(local_path, index=False)
            
        # Re-profile the cleaned data
        profile = profile_data(local_path)
        
        # Update metadata in storage/db
        with open(local_path, "rb") as f:
            file_bytes = f.read()
            
        base_id = session_id.split(":")[0]
        db_service.upload_file("datasets", s3_path, file_bytes, "application/octet-stream")
        
        # Update dataset profile in database
        updated_dataset = db_service.create_dataset(session_id, file_name, s3_path, profile)
        
        return {
            "success": True,
            "dataset": updated_dataset,
            "profile": profile
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}/dataset")
async def get_session_dataset(session_id: str):
    try:
        dataset = db_service.get_dataset_by_session(session_id)
        if not dataset:
            return None
        return dataset
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

@app.delete("/api/messages/{message_id}/chart")
async def delete_message_chart(message_id: str):
    try:
        if not db_service.client:
            # Local mock mode
            for session_id, msgs in db_service.mock_messages.items():
                for m in msgs:
                    if m.get("id") == message_id:
                        m["chart_url"] = None
                        m["chart_summary"] = None
                        return {"success": True}
            raise HTTPException(status_code=404, detail="Message not found.")
        else:
            db_service.client.table("messages").update({
                "chart_url": None,
                "chart_summary": None
            }).eq("id", message_id).execute()
            return {"success": True}
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
        response = process_query(session_id, request.question, schema, local_path, request.chart_url)
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
    base_id = session_id.split(":")[0]
    storage_path = f"{base_id}/dataset.csv"
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

from fastapi.responses import RedirectResponse

@app.get("/api/charts/signed/{session_id}/{filename}")
async def get_signed_chart(session_id: str, filename: str):
    # If in local fallback (no Supabase client)
    if not db_service.client:
        local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../local_storage/charts"))
        file_path = os.path.join(local_storage_dir, session_id, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Chart not found in local storage.")
        return FileResponse(file_path)
    
    # If we have Supabase client, generate a signed URL and redirect to it
    s3_path = f"{session_id}/{filename}"
    try:
        signed_url = db_service.generate_signed_url("charts", s3_path)
        if not signed_url:
            raise HTTPException(status_code=404, detail="Chart not found in storage.")
        return RedirectResponse(url=signed_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
