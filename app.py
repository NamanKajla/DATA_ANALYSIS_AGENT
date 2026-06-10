import os
import sys
from data_loader import clean_source_code, get_schema, load_data
from executor import run_code
from llm import explain_result, get_plan, handle_conversational, route_question
from validator import is_safe_code

print("=====================================================")
print("📊 AUTONOMOUS DATA ANALYSIS AGENT ACTIVE             ")
print("=====================================================")

# --- Step 1: Session Data Ingestion & Auto-Profiling ---
while True:
    file_path = input("📁 Enter file path (CSV, Excel, JSON): ").strip()
    try:
        df = load_data(file_path)
        schema = get_schema(df)
        print("\n✅ Dataset Profile Formulated Successfully!")
        print(f"Columns Discovered: {schema['columns']}")
        break
    except Exception as e:
        print(f"❌ Ingestion Error: {e}. Try again.")

# Global Session Memory Store Arrays
session_history = []

# --- Step 2: Continuous Orchestration Loop ---
while True:
    question = input("\n💬 Ask a question (or type 'exit'): ").strip()

    if not question:
        continue

    if question.lower() in ["exit", "quit"]:
        print("Ending session safely. Goodbye! 👋")
        sys.exit(0)

    # 1. Pipeline Routing Token Parsing
    intent = route_question(question, session_history)

    if intent in ["CHIT_CHAT", "CLARIFICATION"]:
        ai_reply = handle_conversational(question, schema, session_history)
        print(f"\nAI: {ai_reply}")
        session_history.append({"role": "user", "content": question})
        session_history.append({"role": "assistant", "content": ai_reply})
        continue

    # 2. Execution Routing Logic & Autonomous Error Self-Healing Loop
    print("🤖 Thinking and drafting execution strategy...")

    max_retries = 3
    retry_count = 0
    error_feedback = None
    code_execution_success = False
    final_output_result = None
    chart_produced = False

    while retry_count < max_retries:
        try:
            # Request plan configuration
            plan = get_plan(question, schema, session_history, error_feedback)
            raw_code = plan["python_code"]
            cleaned_code = clean_source_code(raw_code)

            # Static Analysis Gate
            is_safe, security_msg = is_safe_code(cleaned_code)
            if not is_safe:
                print(f"⚠️ Security Guardrail Intervention: {security_msg}")
                error_feedback = f"Security Exception Block: {security_msg}. Please re-write."
                retry_count += 1
                continue

            # Isolated Sandbox Execution Step
            success, execution_result, chart_produced = run_code(cleaned_code, df)

            if not success:
                # Code execution failed. Log feedback and auto-retry
                print(
                    f"⚠️ Execution Attempt {retry_count + 1} failed. Activating self-correction loops..."
                )
                error_feedback = execution_result
                retry_count += 1
                continue

            # Execution Cleared!
            final_output_result = execution_result
            code_execution_success = True
            break

        except Exception as system_loop_exception:
            error_feedback = str(system_loop_exception)
            retry_count += 1

    if not code_execution_success:
        print(
            "\n❌ Agent Error: Unable to run calculations safely after multiple self-correction updates."
        )
        print(f"Final error stack logged: {error_feedback}")
        continue

    # Print out working verified code block script
    print("\nVerified Analysis Code Executed:")
    print("-" * 50)
    print(cleaned_code)
    print("-" * 50)

    if chart_produced:
        print("🎨 Chart output generated and saved locally as 'output_chart.png'")

    # 3. Compile Narrative Findings Summary
    print("📝 Compiling analytical brief report...")
    narrative_summary = explain_result(question, final_output_result, chart_produced)

    print("\n" + "=" * 50)
    print(narrative_summary)
    print("=" * 50)

    # Commit step state updates to permanent Session Context History
    session_history.append({"role": "user", "content": question})
    session_history.append(
        {
            "role": "assistant",
            "content": f"Executed Code context trace:\n{cleaned_code}\nResult payload computed: {final_output_result}",
            "code": cleaned_code,
        }
    )