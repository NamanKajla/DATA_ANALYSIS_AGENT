# pyrefly: ignore [missing-import]
import os
# pyrefly: ignore [missing-import]
from supabase import create_client, Client
from .config import settings

class SupabaseService:
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            # Fallback or stub for local dev without credentials
            self.client = None
            self.mock_sessions = []
            self.mock_datasets = {} # session_id -> dataset
            self.mock_messages = {} # session_id -> list of messages
        else:
            self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    def create_session(self, title: str) -> dict:
        """Creates a new user chat session."""
        if not self.client:
            import uuid
            from datetime import datetime
            session = {
                "id": str(uuid.uuid4()),
                "title": title,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            self.mock_sessions.append(session)
            return session
        
        response = self.client.table("sessions").insert({"title": title}).execute()
        return response.data[0] if response.data else {}

    def rename_session(self, session_id: str, new_title: str) -> dict:
        """Renames a chat session."""
        if not self.client:
            for session in self.mock_sessions:
                if session["id"] == session_id:
                    session["title"] = new_title
                    return session
            return {}
        
        response = self.client.table("sessions").update({"title": new_title}).eq("id", session_id).execute()
        return response.data[0] if response.data else {}

    def get_sessions(self) -> list[dict]:
        """Lists all chat sessions."""
        if not self.client:
            return self.mock_sessions
        
        response = self.client.table("sessions").select("*").order("created_at", desc=True).execute()
        return response.data

    def delete_session(self, session_id: str) -> bool:
        """Deletes a chat session and cascades to messages/datasets."""
        if not self.client:
            self.mock_sessions = [s for s in self.mock_sessions if s["id"] != session_id]
            self.mock_datasets.pop(session_id, None)
            self.mock_messages.pop(session_id, None)
            return True
        
        self.client.table("sessions").delete().eq("id", session_id).execute()
        return True

    def create_dataset(self, session_id: str, file_name: str, s3_path: str, schema_json: dict) -> dict:
        """Stores dataset metadata and schema JSON profile."""
        if not self.client:
            from datetime import datetime
            dataset = {
                "id": "mock-dataset-id",
                "session_id": session_id,
                "file_name": file_name,
                "s3_path": s3_path,
                "schema_json": schema_json,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            self.mock_datasets[session_id] = dataset
            return dataset
        
        response = self.client.table("datasets").insert({
            "session_id": session_id,
            "file_name": file_name,
            "s3_path": s3_path,
            "schema_json": schema_json
        }).execute()
        return response.data[0] if response.data else {}

    def get_dataset_by_session(self, session_id: str) -> dict:
        """Gets dataset details linked to a session."""
        if not self.client:
            return self.mock_datasets.get(session_id, {})
        
        response = self.client.table("datasets").select("*").eq("session_id", session_id).execute()
        return response.data[0] if response.data else {}

    def save_message(self, session_id: str, role: str, content: str, generated_code: str = None, chart_url: str = None, follow_ups: list = None, chart_summary: str = None) -> dict:
        """Saves a message in the chat history."""
        if not self.client:
            import uuid
            from datetime import datetime
            message = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "role": role,
                "content": content,
                "generated_code": generated_code,
                "chart_url": chart_url,
                "chart_summary": chart_summary,
                "follow_ups": follow_ups or [],
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            if session_id not in self.mock_messages:
                self.mock_messages[session_id] = []
            self.mock_messages[session_id].append(message)
            return message
        
        payload = {
            "session_id": session_id,
            "role": role,
            "content": content
        }
        if generated_code:
            payload["generated_code"] = generated_code
        if chart_url:
            payload["chart_url"] = chart_url
        if follow_ups:
            payload["follow_ups"] = follow_ups
        if chart_summary:
            payload["chart_summary"] = chart_summary
            
        try:
            response = self.client.table("messages").insert(payload).execute()
            return response.data[0] if response.data else {}
        except Exception:
            if "follow_ups" in payload:
                del payload["follow_ups"]
            if "chart_summary" in payload:
                del payload["chart_summary"]
            response = self.client.table("messages").insert(payload).execute()
            return response.data[0] if response.data else {}

    def get_messages(self, session_id: str) -> list[dict]:
        """Retrieves history of messages for a session."""
        if not self.client:
            return self.mock_messages.get(session_id, [])
        
        response = self.client.table("messages").select("*").eq("session_id", session_id).order("created_at").execute()
        return response.data

    def generate_signed_url(self, bucket_name: str, path: str, expires_in_seconds: int = 3600) -> str:
        """Generates a secure, temporary direct URL to download a file from Supabase Storage."""
        if not self.client:
            # For local fallback, return URL to endpoint in main.py
            filename = path.split("/")[-1]
            return f"http://localhost:8000/api/sessions/{bucket_name}/files/{path}"
        
        response = self.client.storage.from_(bucket_name).create_signed_url(path, expires_in_seconds)
        return response.get("signedURL", "")

    def upload_file(self, bucket_name: str, path: str, file_bytes: bytes, content_type: str) -> str:
        """Uploads raw file content to Supabase Storage and returns storage path."""
        if not self.client:
            # Save file locally inside a dedicated folder for static asset serving
            local_storage_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../local_storage/{bucket_name}"))
            os.makedirs(os.path.dirname(os.path.join(local_storage_dir, path)), exist_ok=True)
            with open(os.path.join(local_storage_dir, path), "wb") as f:
                f.write(file_bytes)
            return path
        
        self.client.storage.from_(bucket_name).upload(path, file_bytes, {"content-type": content_type})
        return path

db_service = SupabaseService()
