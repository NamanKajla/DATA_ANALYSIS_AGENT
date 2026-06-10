import os
import textwrap
import pandas as pd


def load_data(path: str) -> pd.DataFrame:
    """Supports CSV, Excel, and JSON ingestion."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found at: '{path}'")

    ext = os.path.splitext(path)[-1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    elif ext in [".xls", ".xlsx"]:
        return pd.read_excel(path)
    elif ext == ".json":
        return pd.read_json(path)
    else:
        raise ValueError("Unsupported format! Please provide a CSV, Excel, or JSON file.")


def get_schema(df: pd.DataFrame) -> dict:
    """Profiles data automatically: schema, null rates, distributions, anomalies."""
    profile = {"columns": list(df.columns), "dtypes": {}, "null_rates": {}, "anomalies": {}}

    for col in df.columns:
        profile["dtypes"][col] = str(df[col].dtype)
        profile["null_rates"][col] = f"{(df[col].isnull().sum() / len(df)) * 100:.2f}%"

        
        if pd.api.types.is_numeric_dtype(df[col]):
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
            profile["anomalies"][col] = (
                f"{len(outliers)} anomalous data points detected outside standard boundaries."
                if not outliers.empty
                else "No significant statistical anomalies detected."
            )
        else:
            profile["anomalies"][col] = "N/A (Non-numeric field)"

    return profile


def clean_source_code(code: str) -> str:
    """Cleans code strings by removing markdown fragments and structural mis-indents."""
    if not code:
        return ""
  
    code = code.replace("```python", "").replace("```", "")
   
    return textwrap.dedent(code).strip()