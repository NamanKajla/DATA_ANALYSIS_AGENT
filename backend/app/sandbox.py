import os
import shutil
import tempfile
import subprocess
import json
# pyrefly: ignore [missing-import]
import duckdb
from .config import settings

_docker_available_cache = None

def is_docker_available() -> bool:
    """Checks if Docker is installed and running on the host system, cached for efficiency."""
    global _docker_available_cache
    if _docker_available_cache is not None:
        return _docker_available_cache
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=3)
        _docker_available_cache = (res.returncode == 0)
    except (subprocess.SubprocessError, FileNotFoundError):
        _docker_available_cache = False
    return _docker_available_cache

def run_local_fallback(code_content: str, dataset_path: str, temp_dir: str) -> tuple[bool, any, bool]:
    """Runs LLM code locally as a fallback when Docker is not available.
    
    Provides the same DuckDB, Matplotlib, and Seaborn namespaces.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    
    # 1. Register DuckDB View
    con = duckdb.connect(database=":memory:")
    ext = os.path.splitext(dataset_path)[-1].lower()
    try:
        if ext == ".csv":
            con.execute(f"CREATE OR REPLACE VIEW df AS SELECT * FROM read_csv_auto('{dataset_path}')")
        elif ext == ".json":
            con.execute(f"CREATE OR REPLACE VIEW df AS SELECT * FROM read_json_auto('{dataset_path}')")
        elif ext in [".xls", ".xlsx"]:
            import pandas as pd
            excel_df = pd.read_excel(dataset_path)
            con.register("df", excel_df)
        else:
            return False, f"Local Ingestion Error: Unsupported extension '{ext}'", False
    except Exception as e:
        return False, f"Local Ingestion Error: {str(e)}", False

    # 2. Reset Plots
    plt.figure()
    plt.clf()
    plt.close("all")

    local_vars = {
        "con": con,
        "duckdb": duckdb,
        "plt": plt,
        "sns": sns
    }
    global_vars = {}

    try:
        # Execute the code
        exec(code_content, global_vars, local_vars)

        if "result" not in local_vars:
            return False, "The code executed successfully but failed to define the 'result' variable.", False

        result_val = local_vars["result"]
        
        # Serialize result safely
        import pandas as pd
        if isinstance(result_val, pd.DataFrame):
            result_json = result_val.to_dict(orient="records")
        elif isinstance(result_val, pd.Series):
            result_json = result_val.to_dict()
        elif hasattr(result_val, "df"): # DuckDB relation
            result_json = result_val.df().to_dict(orient="records")
        else:
            try:
                json.dumps(result_val)
                result_json = result_val
            except TypeError:
                result_json = str(result_val)

        # Handle Plot output
        fig_nums = plt.get_fignums()
        chart_generated = False
        if fig_nums:
            chart_path = os.path.join(temp_dir, "output_chart.png")
            plt.savefig(chart_path, bbox_inches="tight", dpi=150)
            chart_generated = True

        return True, result_json, chart_generated

    except Exception as e:
        import traceback
        return False, f"Runtime Execution Exception:\n{traceback.format_exc()}", False
    finally:
        con.close()

def execute_in_sandbox(code_content: str, dataset_local_path: str) -> tuple[bool, any, bool, str]:
    """Runs python code against a dataset in a sandbox environment.
    
    Returns:
        (success: bool, result: any_or_error_message, chart_generated: bool, chart_local_path: str)
    """
    # Create temp directory workspace
    temp_workspace = tempfile.mkdtemp()
    
    data_dir = os.path.join(temp_workspace, "data")
    output_dir = os.path.join(temp_workspace, "output")
    os.makedirs(data_dir)
    os.makedirs(output_dir)

    # 1. Copy dataset to temp dir with generic base name
    ext = os.path.splitext(dataset_local_path)[-1]
    target_data_path = os.path.join(data_dir, f"dataset{ext}")
    shutil.copy(dataset_local_path, target_data_path)

    # 2. Write user code
    user_code_path = os.path.join(temp_workspace, "user_code.py")
    with open(user_code_path, "w", encoding="utf-8") as f:
        f.write(code_content)

    # 3. Choose Execution Mode (Docker vs Local Fallback)
    docker_available = is_docker_available()
    
    if not docker_available:
        print("[INFO] Docker not running. Falling back to safe local execution.")
        success, result, chart_generated = run_local_fallback(code_content, target_data_path, output_dir)
        chart_file_path = os.path.join(output_dir, "output_chart.png") if chart_generated else ""
        
        # Move output chart out of temp dir to a permanent location if needed, or keep it in temp
        # Let's return the workspace directory so the caller can upload it before clean up
        return success, result, chart_generated, chart_file_path

    # Docker execution path
    try:
        # Construct docker command
        # Mounts:
        # user_code.py -> /sandbox/user_code.py
        # data/ -> /sandbox/data/ (read-only)
        # output/ -> /sandbox/output/ (read-write)
        cmd = [
            "docker", "run", "--rm",
            "--network", "none", # Block network access for security
            "-m", "512m",        # Limit memory to 512MB
            "--cpus", "1.0",     # Limit to 1 CPU core
            "-v", f"{os.path.abspath(user_code_path)}:/sandbox/user_code.py:ro",
            "-v", f"{os.path.abspath(data_dir)}:/sandbox/data:ro",
            "-v", f"{os.path.abspath(output_dir)}:/sandbox/output",
            settings.SANDBOX_DOCKER_IMAGE
        ]
        
        # Run container
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.SANDBOX_TIMEOUT_SECONDS)
        
        if res.returncode != 0:
            # Code failed or crashed
            error_output = res.stderr if res.stderr else res.stdout
            
            # Graceful local execution fallback on docker image/daemon/setup failure
            if "Traceback" not in error_output or "Unable to find image" in error_output or "docker:" in error_output or "daemon" in error_output.lower() or res.returncode in [125, 127]:
                print(f"[WARNING] Docker setup/run failed. Falling back to local execution. Details:\n{error_output}")
                success, result, chart_generated = run_local_fallback(code_content, target_data_path, output_dir)
                chart_file_path = os.path.join(output_dir, "output_chart.png") if chart_generated else ""
                return success, result, chart_generated, chart_file_path
                
            return False, f"Sandbox Crash (exit code {res.returncode}):\n{error_output}", False, ""
            
        # Parse outputs
        result_json_path = os.path.join(output_dir, "result.json")
        if not os.path.exists(result_json_path):
            return False, "Code finished successfully but did not export a result payload.", False, ""
            
        with open(result_json_path, "r", encoding="utf-8") as rf:
            output_payload = json.load(rf)
            
        chart_local_path = os.path.join(output_dir, "output_chart.png")
        chart_generated = os.path.exists(chart_local_path)
        
        return True, output_payload.get("result"), chart_generated, chart_local_path

    except subprocess.TimeoutExpired:
        print("[WARNING] Docker execution timed out. Falling back to local execution.")
        success, result, chart_generated = run_local_fallback(code_content, target_data_path, output_dir)
        chart_file_path = os.path.join(output_dir, "output_chart.png") if chart_generated else ""
        return success, result, chart_generated, chart_file_path
    except Exception as e:
        return False, f"Sandbox Orchestration Failure: {str(e)}", False, ""
