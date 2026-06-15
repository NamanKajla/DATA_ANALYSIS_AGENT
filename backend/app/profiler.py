import os
import duckdb
import pandas as pd

def load_file_into_duckdb(con: duckdb.DuckDBPyConnection, filepath: str) -> str:
    """Loads a file into a DuckDB connection as a temporary view.
    
    Supports CSV, JSON, and Excel (via pandas registration).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found at: '{filepath}'")

    ext = os.path.splitext(filepath)[-1].lower()
    view_name = "data_source"
    
    if ext == ".csv":
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_csv_auto('{filepath}')")
    elif ext == ".json":
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_json_auto('{filepath}')")
    elif ext in [".xls", ".xlsx"]:
        # Fallback to pandas for Excel, then register the dataframe in DuckDB
        df = pd.read_excel(filepath)
        con.register(view_name, df)
    else:
        raise ValueError(f"Unsupported format: {ext}. Only CSV, Excel, and JSON are supported.")
        
    return view_name

def profile_data(filepath: str) -> dict:
    """Generates a complete metadata profile of the dataset using DuckDB.
    
    Returns a dictionary containing:
        - columns: list of column names
        - dtypes: dictionary mapping columns to types
        - null_rates: dictionary of null rates in percentage
        - anomalies: dictionary with outlier analysis descriptions
        - total_rows: total number of rows
    """
    con = duckdb.connect(database=":memory:")
    try:
        view_name = load_file_into_duckdb(con, filepath)
        
        # 1. Get Row Count
        total_rows = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
        if total_rows == 0:
            return {"columns": [], "dtypes": {}, "null_rates": {}, "anomalies": {}, "total_rows": 0}

        # 2. Get Column info
        info = con.execute(f"PRAGMA table_info({view_name})").fetchall()
        # info columns: (cid, name, type, notnull, dflt_value, pk)
        columns = [row[1] for row in info]
        dtypes = {row[1]: row[2] for row in info}

        # 3. Get Null rates (done in a single optimized query)
        null_rates = {}
        if columns:
            null_select_parts = [f"SUM(CASE WHEN \"{col}\" IS NULL THEN 1 ELSE 0 END) AS \"{col}_nulls\"" for col in columns]
            null_query = f"SELECT {', '.join(null_select_parts)} FROM {view_name}"
            null_counts = con.execute(null_query).fetchone()
            
            for col, count in zip(columns, null_counts):
                null_rates[col] = f"{(count / total_rows) * 100:.2f}%"

        # 4. Outlier & Statistical Anomaly Profiling + Descriptive Stats
        anomalies = {}
        numerical_stats = {}
        for col in columns:
            col_type = dtypes[col].upper()
            is_numeric = any(t in col_type for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT"])
            
            if is_numeric:
                # Calculate IQR and descriptive stats in a single DuckDB query
                stats_query = f"""
                    SELECT 
                        approx_quantile("{col}", 0.25) AS q1,
                        approx_quantile("{col}", 0.75) AS q3,
                        AVG("{col}") AS mean_val,
                        approx_quantile("{col}", 0.5) AS median_val,
                        MIN("{col}") AS min_val,
                        MAX("{col}") AS max_val,
                        STDDEV_SAMP("{col}") AS std_val
                    FROM {view_name}
                """
                stats = con.execute(stats_query).fetchone()
                q1, q3, mean_val, median_val, min_val, max_val, std_val = stats
                
                # Save numerical stats
                numerical_stats[col] = {
                    "mean": f"{mean_val:.2f}" if mean_val is not None else "N/A",
                    "median": f"{median_val:.2f}" if median_val is not None else "N/A",
                    "min": f"{min_val:.2f}" if min_val is not None else "N/A",
                    "max": f"{max_val:.2f}" if max_val is not None else "N/A",
                    "std": f"{std_val:.2f}" if std_val is not None else "N/A"
                }
                
                if q1 is not None and q3 is not None:
                    iqr = q3 - q1
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    
                    # Count outliers
                    outlier_query = f"""
                        SELECT COUNT(*) 
                        FROM {view_name} 
                        WHERE "{col}" < {lower_bound} OR "{col}" > {upper_bound}
                    """
                    outlier_count = con.execute(outlier_query).fetchone()[0]
                    
                    if outlier_count > 0:
                        anomalies[col] = f"{outlier_count} anomalous data points detected outside standard boundaries (IQR)."
                    else:
                        anomalies[col] = "No significant statistical anomalies detected."
                else:
                    anomalies[col] = "Insufficient data to compute anomalies."
            else:
                anomalies[col] = "N/A (Non-numeric field)"

        return {
            "columns": columns,
            "dtypes": dtypes,
            "null_rates": null_rates,
            "anomalies": anomalies,
            "numerical_stats": numerical_stats,
            "total_rows": total_rows
        }
    finally:
        con.close()
