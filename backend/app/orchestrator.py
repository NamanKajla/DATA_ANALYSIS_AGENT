import json
import os
import textwrap
from groq import Groq
from .config import settings
from .sandbox import execute_in_sandbox
from .database import db_service

# Initialize Groq Client
client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

def route_question(question: str, history: list) -> str:
    """Identifies user's conversational intent based on context."""
    if not client:
        return "DATA_QUERY" # Default fallback for local testing
        
    system_prompt = (
        "You are a routing classification assistant. Classify the user's input into exactly ONE category token:\n"
        "- 'DATA_QUERY': If the user is asking for calculations, metrics (mean, median, count, sum, min, max), data analysis, data aggregation, "
        "filtering, grouping, visualizations/plots, unique/distinct values, displaying column contents, listing actual records, or general data manipulation "
        "that requires running code on the loaded dataset. Crucially, if the user asks to see, list, or name actual values present in any column (e.g. 'name all names present in the brand column'), this is a DATA_QUERY.\n"
        "- 'CHIT_CHAT': Basic greetings (hello, hi, how are you), thanking the agent (thanks, thank you), or off-topic conversation.\n"
        "- 'CLARIFICATION': Questions about the application itself, how to use it, or general questions about what columns or types "
        "exist in the dataset schema, without requesting any actual data records, calculations, or unique values.\n\n"
        "Reply with ONLY the token string ('DATA_QUERY', 'CHIT_CHAT', or 'CLARIFICATION') and nothing else."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-3:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(model=settings.MODEL_NAME, messages=messages, temperature=0)
    if response.usage:
        print(f"[Groq Token Usage - Route] Model: {response.model} | Prompt: {response.usage.prompt_tokens} | Completion: {response.usage.completion_tokens} | Total: {response.usage.total_tokens}")
    return response.choices[0].message.content.strip()

def handle_conversational(question: str, schema: dict, history: list) -> tuple[str, list[str]]:
    """Answers conversational or clarification queries without executing code."""
    if not client:
        return "I am ready to help you analyze your data. Please upload a dataset to begin.", ["How can I import a dataset?", "What operations can I perform?"]
        
    system_prompt = f"""You are a helpful data analyst assistant. Chat with the user naturally. Dataset schema context: {schema}
    
    You must output a JSON object matching this schema exactly:
    {{
      "reply": "Your conversational reply here",
      "follow_ups": ["Short follow-up question 1", "Short follow-up question 2"]
    }}
    
    CRITICAL: The follow-up questions must be written from the USER's perspective asking the AI (e.g. "Can you compare...", "Show me...", "Explain why..."), NOT what the AI would ask the user.
    """
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    for msg in history[-5:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            response_format={"type": "json_object"},
            messages=messages,
            temperature=0.5
        )
        if response.usage:
            print(f"[Groq Token Usage - Chat] Model: {response.model} | Prompt: {response.usage.prompt_tokens} | Completion: {response.usage.completion_tokens} | Total: {response.usage.total_tokens}")
        data = json.loads(response.choices[0].message.content)
        return data.get("reply", ""), data.get("follow_ups", [])
    except Exception:
        return "I am ready to help you analyze your data.", ["What columns are in the dataset?", "Can you show statistics?"]

def get_plan(question: str, schema: dict, history: list, error_feedback: str = None) -> dict:
    """Assembles Python scripts designed to execute on a DuckDB database connection."""
    if not client:
        # Static local stub for fallback testing
        return {
            "python_code": "result = con.sql(\"SELECT * FROM df LIMIT 5\").df()",
            "explanation": "Query first 5 rows"
        }
        
    system_prompt = f"""You are an elite automated Python data analyst agent. Write clean Python analytics scripts to process a DuckDB database.
    
    CRITICAL ARCHITECTURE CONSTRAINTS:
    1. The source data frame structure is ALREADY loaded as a temporary view in the DuckDB connection under the name: `df`
    2. CRITICAL: Never write 'import duckdb', 'import pandas', 'import seaborn', or 'import matplotlib'. These libraries are already loaded in the environment namespace. Jump straight to using variables `con`, `sns`, or `plt`.
    3. You MUST save the final computed data object (e.g., a DataFrame, a Series, a number, a list, or a dictionary) into a variable named exactly `result` (e.g., `result = con.sql("SELECT * FROM df").df()`).
    4. WARNING: Do NOT write long conversational text sentences or narrative paragraphs inside the python code or assign them to `result`. Keep the python code strictly focused on data calculations and plotting.
    5. If a visualization (chart) is useful for this query, write matplotlib/seaborn code to construct it. Do NOT call `plt.show()`. The sandbox handles saving it.
    6. MULTIPLE PLOTS RULE: If you need to generate more than one chart to answer a question, do NOT call `plt.figure()` multiple times. Instead, combine them into a single image canvas using subplots (e.g., `plt.subplot(nrows, ncols, index)`) so all visual elements are captured together in the final saved file.
    7. JSON STRUCTURE RULE: Ensure your script is a safely formatted string asset inside the JSON. Do not forget to close the "python_code" string value with a double quote (") and a comma (,) before opening the "explanation" key structure.
    8. COLUMN IDENTIFIER RULE: Column names containing spaces or special characters MUST be wrapped in double quotes in your SQL queries (e.g., `con.sql('SELECT "Column Name" FROM df')`) or accessed with proper string index keys in Pandas. Check the schema column names carefully. Only use column names that are actually present in the dataset schema. If the user refers to a column by a synonym or typo (e.g. 'stokck prices' or 'brand name'), map it to the closest match in the schema columns (like 'Price', 'Stock', 'Brand', or 'Name') based on the schema column list. Do not invent or guess columns that do not exist.
    9. COMPLEX STRING FORMATS: If a column contains comma-separated values (e.g., "1001, 1002, 1003"), do not apply arithmetic functions (like AVG or SUM) directly in SQL. Instead, load the column using `con.sql(...)` into a Pandas DataFrame, parse/split the strings in Python to extract individual values, and perform your calculation in Python.
    10. SEABORN DATA RULE: When using seaborn plotting functions (like `sns.barplot`, `sns.lineplot`, `sns.scatterplot`, etc.), you MUST pass the pandas DataFrame containing the columns as the `data` parameter (e.g. `sns.barplot(x="Brand", y="Price", data=result)`). Do not call seaborn plotting methods without passing the `data` parameter.
    11. MATPLOTLIB PLOTTING RULE: When using `plt.subplots()`, it returns a tuple `(fig, ax)`. You MUST call plotting methods on the axis object `ax` (e.g., `ax.plot(...)`, `ax.bar(...)`), not on the axis tuple or figure object.
    12. HIGH CARDINALITY RULE: If a column has high cardinality (more than 15-20 unique values) and you are plotting a bar chart, count plot, or other categorical plot, you MUST limit it to the top 10-15 categories (e.g. using `LIMIT 15` in SQL or `.head(15)` in Pandas) to ensure the plot is clean, readable, and executes quickly. Never attempt to plot categorical charts with dozens, hundreds, or thousands of categories, as this will hang the sandbox container or cause out-of-memory crashes.
    
    Dataset Auto-Profile Summary (columns, types, nulls):
    {schema}
    
    Your response must map explicitly to this JSON schema layout:
    {{
      "python_code": "Your formatted python code lines here",
      "explanation": "Brief structural description"
    }}
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history[-6:]:
        if "code" not in msg:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    if error_feedback:
        messages.append({
            "role": "system",
            "content": f"⚠️ PREVIOUS CODE EXECUTION FAILED WITH EXCEPTION:\n{error_feedback}\nFix the logic, eliminate bad indents, and return updated code."
        })

    response = client.chat.completions.create(
        model=settings.MODEL_NAME,
        response_format={"type": "json_object"},
        messages=messages,
        temperature=0
    )
    if response.usage:
        print(f"[Groq Token Usage - Plan] Model: {response.model} | Prompt: {response.usage.prompt_tokens} | Completion: {response.usage.completion_tokens} | Total: {response.usage.total_tokens}")
    
    return json.loads(response.choices[0].message.content)

def clean_source_code(code: str) -> str:
    """Cleans code strings by removing markdown fragments and structural mis-indents."""
    if not code:
        return ""
    code = code.replace("```python", "").replace("```", "")
    return textwrap.dedent(code).strip()

def explain_result(question: str, result: any, has_chart: bool) -> tuple[str, list[str], str]:
    """Compiles the narrative summary, calling out key insights, constraints, and follow-ups."""
    if not client:
        return f"Calculation completed successfully. Result: {result}", ["Can we run another query?", "Can you plot this?"], "A simple results visualization."
        
    system_prompt = """Review the executed analytical data metrics and generate a concise and clear explanation.
    
    You must output a JSON object matching this schema exactly:
    {
      "explanation": "A natural, conversational narrative explaining the findings. Use headings, bold text, or bullet points dynamically ONLY if they are helpful and appropriate for structuring the data (e.g. for listing categories or summarizing findings). Do not use boilerplate labels or rigid templates.",
      "chart_summary": "A 1-sentence description of the visual chart layout, trends, axes, and contents (only if a chart was generated, otherwise output empty string or N/A)",
      "follow_ups": ["Short follow-up question 1", "Short follow-up question 2"]
    }
    
    CRITICAL: The follow-up questions must be written from the USER's perspective asking the AI (e.g. "Can you compare...", "Show me...", "Explain why..."), NOT what the AI would ask the user.
    """
    
    str_result = str(result)
    if len(str_result) > 2000:
        str_result = str_result[:2000] + "\n... [Output truncated for conciseness] ..."

    user_content = f"User Question: {question}\nData Calculations Value Output: {str_result}"
    if has_chart:
        user_content += "\nNote: A matching visual visualization file plot chart asset has been compiled."

    try:
        response = client.chat.completions.create(
            model=settings.MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2
        )
        # Log token usage
        if response.usage:
            print(f"[Groq Token Usage - Explain] Model: {response.model} | Prompt: {response.usage.prompt_tokens} | Completion: {response.usage.completion_tokens} | Total: {response.usage.total_tokens}")
            
        data = json.loads(response.choices[0].message.content)
        content = data.get("explanation", "Calculation completed successfully.")
        chart_summary = data.get("chart_summary", "")
        follow_ups = data.get("follow_ups", [])
        return content, follow_ups, chart_summary
    except Exception:
        fallback_text = f"Calculation completed successfully. Result: {result}"
        return fallback_text, ["Analyze this column in more detail?", "Generate a plot for this data?"], ""

def process_query(session_id: str, question: str, schema: dict, dataset_local_path: str) -> dict:
    """Main execution loop for user questions. Runs intent routing, code execution retry loop,
    and narrative explanation synthesis.
    """
    history = db_service.get_messages(session_id)
    
    # Filter out failed query turns from history to prevent context contamination
    filtered_history = []
    i = 0
    while i < len(history):
        if (i < len(history) - 1 and 
            history[i]["role"] == "user" and 
            history[i+1]["role"] == "assistant" and 
            history[i+1]["content"] == settings.FALLBACK_ERROR_MESSAGE):
            i += 2
        else:
            filtered_history.append(history[i])
            i += 1
    history = filtered_history
    
    # 1. Intent Classification
    intent = route_question(question, history)
    
    if intent in ["CHIT_CHAT", "CLARIFICATION"]:
        ai_reply, follow_ups = handle_conversational(question, schema, history)
        db_service.save_message(session_id, "user", question)
        db_service.save_message(session_id, "assistant", ai_reply, None, None, follow_ups)
        return {
            "role": "assistant",
            "content": ai_reply,
            "generated_code": None,
            "chart_url": None,
            "follow_ups": follow_ups
        }

    # 2. Code Generation & Execution Sisyphus loop
    error_feedback = None
    success = False
    result_val = None
    chart_generated = False
    chart_path = ""
    cleaned_code = ""
    
    for attempt in range(settings.MAX_RETRIES):
        try:
            # Generate code plan
            plan = get_plan(question, schema, history, error_feedback)
            raw_code = plan.get("python_code", "")
            cleaned_code = clean_source_code(raw_code)
            
            # Execute code inside the sandbox
            success, result_val, chart_generated, chart_path = execute_in_sandbox(cleaned_code, dataset_local_path)
            
            if success:
                break
            else:
                error_feedback = str(result_val)
                print(f"[SANDBOX EXECUTION ERROR] Attempt {attempt + 1} failed:\n{error_feedback}")
        except Exception as e:
            error_feedback = str(e)
            print(f"[ORCHESTRATOR LOOP EXCEPTION]: {error_feedback}")
            
    if not success:
        # Enforce retry limit fallback error message
        db_service.save_message(session_id, "user", question)
        db_service.save_message(session_id, "assistant", settings.FALLBACK_ERROR_MESSAGE)
        return {
            "role": "assistant",
            "content": settings.FALLBACK_ERROR_MESSAGE,
            "generated_code": None,
            "chart_url": None,
            "follow_ups": ["What columns are available in this dataset?", "Can you show me a summary of the dataset structure?", "Provide a statistical summary of the table"]
        }

    # 3. Save generated plot (if any) to Supabase Storage
    chart_url = None
    if chart_generated and chart_path and os.path.exists(chart_path):
        try:
            # Load bytes
            with open(chart_path, "rb") as f:
                chart_bytes = f.read()
            # Upload to Storage bucket
            storage_filename = f"{session_id}/chart_{attempt}.png"
            db_service.upload_file("charts", storage_filename, chart_bytes, "image/png")
            # Generate temporary signed URL
            chart_url = db_service.generate_signed_url("charts", storage_filename)
        except Exception as upload_err:
            print(f"Failed to upload chart: {upload_err}")

    # 4. Generate plain-English explanation
    narrative, follow_ups, chart_summary = explain_result(question, result_val, chart_generated)
    
    # Save session records
    db_service.save_message(session_id, "user", question)
    db_service.save_message(session_id, "assistant", narrative, cleaned_code, chart_url, follow_ups, chart_summary)
    
    return {
        "role": "assistant",
        "content": narrative,
        "generated_code": cleaned_code,
        "chart_url": chart_url,
        "chart_summary": chart_summary,
        "follow_ups": follow_ups
    }
