import sys
import matplotlib

# Force headless system execution backend to avoid tk/GUI dependency blockages
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def run_code(code: str, df: pd.DataFrame) -> tuple[bool, any, bool]:
    """Runs code statements in an isolated variable sandbox.

    Returns:
        (success_status, output_result, chart_generated)
    """
    # Reset internal plot frames to prevent graph overlapping mixtures
    plt.figure()
    plt.clf()
    plt.close("all")

    local_vars = {"df": df, "pd": pd, "plt": plt, "sns": sns}
    global_vars = {}

    try:
        exec(code, global_vars, local_vars)

        if "result" not in local_vars:
            return (
                False,
                "The logic executed successfully but forgot to store the answer inside the 'result' global variable identifier.",
                False,
            )

        # Evaluate if a figure canvas was drawn to
        fig_nums = plt.get_fignums()
        chart_saved = False
        if fig_nums:
            # Export plot safely to system directory
            plt.savefig("output_chart.png", bbox_inches="tight", dpi=150)
            chart_saved = True

        return True, local_vars["result"], chart_saved

    except Exception as e:
        return False, f"Runtime Error Exception: {str(e)}", False