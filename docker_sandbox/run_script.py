import sys
import os
import json
import matplotlib
matplotlib.use("Agg") # Headless
import matplotlib.pyplot as plt
import seaborn as sns
import duckdb

def run_sandbox():
    user_code_path = "/sandbox/user_code.py"
    data_file_path = "/sandbox/data/dataset" # Mounted file without extension, we will auto-detect
    output_dir = "/sandbox/output"
    
    # 1. Detect dataset file extension
    data_files = [f for f in os.listdir("/sandbox/data") if f.startswith("dataset")]
    if not data_files:
        print("Error: No dataset found in /sandbox/data", file=sys.stderr)
        sys.exit(1)
    
    dataset_actual_path = os.path.join("/sandbox/data", data_files[0])
    ext = os.path.splitext(dataset_actual_path)[-1].lower()
    
    # 2. Setup DuckDB Connection and register the view 'df'
    con = duckdb.connect(database=":memory:")
    try:
        if ext == ".csv":
            con.execute(f"CREATE OR REPLACE VIEW df AS SELECT * FROM read_csv_auto('{dataset_actual_path}')")
        elif ext == ".json":
            con.execute(f"CREATE OR REPLACE VIEW df AS SELECT * FROM read_json_auto('{dataset_actual_path}')")
        elif ext in [".xls", ".xlsx"]:
            import pandas as pd
            excel_df = pd.read_excel(dataset_actual_path)
            con.register("df", excel_df)
        else:
            print(f"Error: Unsupported dataset format {ext}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error loading dataset: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Read LLM Code
    if not os.path.exists(user_code_path):
        print(f"Error: User code not found at {user_code_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(user_code_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 4. Execute Code
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
        # Run code in sandbox namespaces
        exec(code, global_vars, local_vars)
        
        if "result" not in local_vars:
            print("Error: The code executed successfully but failed to set the 'result' variable.", file=sys.stderr)
            sys.exit(2)
            
        result_val = local_vars["result"]
        
        # Format result safely to JSON (convert DataFrames, Series, etc. to native types)
        import pandas as pd
        if isinstance(result_val, pd.DataFrame):
            result_json = result_val.to_dict(orient="records")
        elif isinstance(result_val, pd.Series):
            result_json = result_val.to_dict()
        elif hasattr(result_val, "df"): # DuckDB relation
            result_json = result_val.df().to_dict(orient="records")
        else:
            try:
                # Test JSON serializability
                json.dumps(result_val)
                result_json = result_val
            except TypeError:
                result_json = str(result_val)

        # Write result payload
        with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as rf:
            json.dump({"success": True, "result": result_json}, rf, default=str)

        # Check for charts
        fig_nums = plt.get_fignums()
        if fig_nums:
            plt.savefig(os.path.join(output_dir, "output_chart.png"), bbox_inches="tight", dpi=150)
            with open(os.path.join(output_dir, "chart_metadata.json"), "w") as cf:
                json.dump({"has_chart": True}, cf)
                
        sys.exit(0)

    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_sandbox()
