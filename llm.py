import json
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "llama-3.3-70b-versatile"


def route_question(question: str, history: list) -> str:
    """Identifies conversational intent while looking at history context."""
    messages = [
        {
            "role": "system",
            "content": "Classify the input into exactly ONE category token: 'DATA_QUERY', 'CHIT_CHAT', or 'CLARIFICATION'. Reply with only the token string.",
        }
    ]
    
    for msg in history[-3:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(model=MODEL_NAME, messages=messages, temperature=0)
    return response.choices[0].message.content.strip()


def handle_conversational(question: str, schema: dict, history: list) -> str:
    messages = [
        {
            "role": "system",
            "content": f"You are a helpful data analyst assistant. Chat with the user naturally. Dataset schema: {schema}",
        }
    ]
    for msg in history[-5:]:
        messages.append(msg)
    messages.append({"role": "user", "content": question})

    response = client.chat.completions.create(
        model=MODEL_NAME, messages=messages, temperature=0.5
    )
    return response.choices[0].message.content.strip()


def get_plan(question: str, schema: dict, history: list, error_feedback: str = None) -> dict:
    """Assembles programmatic logic sequences leveraging Strict Structured JSON pipelines."""
    system_prompt = f"""You are an elite automated Python data analyst agent. Write clean Pandas/Seaborn analytics scripts.

CRITICAL ARCHITECTURE CONSTRAINTS:
1. The source data frame target structure is ALREADY instantiated under the exact namespace: `df`
2. CRITICAL: Never write 'import pandas', 'import seaborn', or 'import matplotlib'. These libraries are already loaded in the environment namespace. Jump straight to using variables `df`, `sns`, or `plt`.
3. You MUST save the final computed data object (e.g., a DataFrame, a Series, a number, a list, or a dictionary) into a variable named exactly `result` (e.g., `result = df.describe()`). 
4. WARNING: Do NOT write long conversational text sentences or narrative paragraphs inside the python code or assign them to `result`. Keep the python code strictly focused on data calculations and plotting.
5. If a visualization (chart) is useful for this query, write matplotlib/seaborn code to construct it. Do NOT call `plt.show()`. The sandbox handles saving it.
6. MULTIPLE PLOTS RULE: If you need to generate more than one chart to answer a question, do NOT call `plt.figure()` multiple times. Instead, combine them into a single image canvas using subplots (e.g., `plt.subplot(nrows, ncols, index)`) so all visual elements are captured together in the final saved file.
7. JSON STRUCTURE RULE: Ensure your script is a safely formatted string asset inside the JSON. Do not forget to close the "python_code" string value with a double quote (") and a comma (,) before opening the "explanation" key structure.

Dataset Auto-Profile Summary:
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
        messages.append(
            {
                "role": "system",
                "content": f"⚠️ PREVIOUS CODE EXECUTION FAILED WITH EXCEPTION:\n{error_feedback}\nFix the logic, eliminate bad indents, and return updated code.",
            }
        )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        response_format={"type": "json_object"},
        messages=messages,
        temperature=0,
    )

    return json.loads(response.choices[0].message.content)


def explain_result(question: str, result: any, has_chart: bool) -> str:
    """Compiles the narrative summary, calling out key insights, constraints, and follow-ups."""
    system_prompt = """Review the executed analytical data metrics and generate a concise corporate brief.
    
    Keep your response minimal, avoiding walls of text. Use this exact compact layout:
    📊 **Key Insight**: [1-2 sentences translating the data finding]
    🎯 **Business Meaning**: [1 sentence on why this matters to decision-makers]
    ⚠️ **Limitation**: [1 sentence on data gaps, sample size, or uncertainty]
    💡 **Next Steps**: [Provide 2 short follow-up questions, separated by a comma or a single line]
    """

    user_content = f"User Question: {question}\nData Calculations Value Output: {result}"
    if has_chart:
        user_content += "\nNote: A matching visual visualization file plot chart asset has been compiled."

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()