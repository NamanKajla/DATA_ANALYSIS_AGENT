"""
Run with:  python -m pytest backend/tests/test_validator.py -v
"""
import pytest
from backend.app.validator import validate_generated_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_safe(code: str):
    result = validate_generated_code(code)
    assert result.is_safe, f"Expected safe but got blocked: {result.reason}\nCode:\n{code}"


def assert_blocked(code: str, reason_fragment: str = ""):
    result = validate_generated_code(code)
    assert not result.is_safe, f"Expected blocked but passed.\nCode:\n{code}"
    if reason_fragment:
        assert reason_fragment.lower() in result.reason.lower(), (
            f"Expected reason to contain {reason_fragment!r}, got: {result.reason}"
        )


# ---------------------------------------------------------------------------
# Legitimate data-analysis code — should all pass
# ---------------------------------------------------------------------------

class TestLegitimateCode:
    def test_basic_duckdb_query(self):
        assert_safe('result = con.sql("SELECT COUNT(*) FROM df").df()')

    def test_pandas_describe(self):
        assert_safe(
            'df_pd = con.sql("SELECT * FROM df").df()\n'
            'result = df_pd.describe()'
        )

    def test_seaborn_plot(self):
        assert_safe(
            'import_df = con.sql("SELECT brand, price FROM df").df()\n'
            'sns.barplot(x="brand", y="price", data=import_df)\n'
            'result = import_df'
        )

    def test_matplotlib_subplot(self):
        assert_safe(
            'fig, (ax1, ax2) = plt.subplots(1, 2)\n'
            'data = con.sql("SELECT * FROM df").df()\n'
            'ax1.bar(data["a"], data["b"])\n'
            'ax2.hist(data["b"])\n'
            'result = data'
        )

    def test_multiline_aggregation(self):
        assert_safe(
            'result = con.sql("""\n'
            '    SELECT category, AVG(price) as avg_price\n'
            '    FROM df\n'
            '    GROUP BY category\n'
            '    ORDER BY avg_price DESC\n'
            '    LIMIT 10\n'
            '""").df()'
        )

    def test_string_manipulation(self):
        assert_safe(
            'df_pd = con.sql("SELECT name FROM df").df()\n'
            'result = df_pd["name"].str.upper().value_counts()'
        )

    def test_numeric_computation(self):
        assert_safe(
            'import math\n'  # math is not in forbidden list
            'df_pd = con.sql("SELECT price FROM df").df()\n'
            'result = round(df_pd["price"].mean(), 2)'
        )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------

class TestForbiddenImports:
    def test_import_os(self):
        assert_blocked("import os\nresult = os.listdir('.')", "forbidden import")

    def test_import_sys(self):
        assert_blocked("import sys\nresult = sys.version", "forbidden import")

    def test_import_subprocess(self):
        assert_blocked("import subprocess\nresult = subprocess.check_output('ls')", "forbidden import")

    def test_import_socket(self):
        assert_blocked("import socket\ns = socket.socket()\nresult = s", "forbidden import")

    def test_from_os_import(self):
        assert_blocked("from os import listdir\nresult = listdir('.')", "forbidden module import")

    def test_from_os_path(self):
        assert_blocked("from os.path import join\nresult = join('a', 'b')", "forbidden module import")

    def test_import_pickle(self):
        assert_blocked("import pickle\nresult = pickle.dumps({})", "forbidden import")

    def test_import_pathlib(self):
        assert_blocked("from pathlib import Path\nresult = Path('.').iterdir()", "forbidden module import")

    def test_import_threading(self):
        assert_blocked("import threading\nresult = threading.current_thread()", "forbidden import")


# ---------------------------------------------------------------------------
# Forbidden function calls
# ---------------------------------------------------------------------------

class TestForbiddenCalls:
    def test_eval(self):
        assert_blocked("result = eval('1+1')", "forbidden function call")

    def test_exec(self):
        assert_blocked("exec('x=1')\nresult = 1", "forbidden function call")

    def test_open(self):
        assert_blocked("f = open('/etc/passwd')\nresult = f.read()", "forbidden function call")

    def test_compile(self):
        assert_blocked("code = compile('x=1', '<str>', 'exec')\nresult = code", "forbidden function call")

    def test_globals(self):
        assert_blocked("result = globals()", "forbidden function call")

    def test_locals(self):
        assert_blocked("result = locals()", "forbidden function call")

    def test_getattr(self):
        assert_blocked("result = getattr(con, '__class__')", "forbidden function call")


# ---------------------------------------------------------------------------
# Dunder / attribute chain escapes
# ---------------------------------------------------------------------------

class TestDunderEscapes:
    def test_class_escape(self):
        assert_blocked(
            "result = ().__class__.__bases__[0].__subclasses__()",
            "forbidden attribute"
        )

    def test_globals_escape(self):
        assert_blocked(
            "result = (lambda: None).__globals__['__builtins__']",
            "forbidden attribute"
        )

    def test_builtins_escape(self):
        assert_blocked(
            "result = {}.__class__.__builtins__",
            "forbidden attribute"
        )

    def test_dunder_method_call(self):
        assert_blocked(
            "result = con.__getattribute__('execute')",
            "forbidden dunder"
        )

    def test_mro_escape(self):
        assert_blocked(
            "result = int.__mro__",
            "forbidden attribute"
        )


# ---------------------------------------------------------------------------
# Secrets detection
# ---------------------------------------------------------------------------

class TestSecretDetection:
    def test_groq_key_reference(self):
        assert_blocked(
            "import os\nkey = os.environ.get('GROQ_API_KEY')\nresult = key",
            "sensitive secret"
        )

    def test_supabase_url(self):
        assert_blocked(
            "url = 'SUPABASE_URL'\nresult = url",
            "sensitive secret"
        )

    def test_openai_style_key(self):
        assert_blocked(
            "result = 'sk-abcdefghij1234567890abcdefghij'",
            "sensitive secret"
        )

    def test_postgres_connection_string(self):
        assert_blocked(
            "result = 'postgresql://user:pass@host:5432/db'",
            "sensitive secret"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_code(self):
        # Empty code passes validation (sandbox will fail with 'result not defined')
        assert_safe("")

    def test_code_too_long(self):
        huge = "result = 1\n" + "# padding\n" * 1000
        assert_blocked(huge, "maximum allowed length")

    def test_large_range_literal(self):
        assert_blocked(
            "for i in range(999999):\n    pass\nresult = i",
            "large range"
        )

    def test_shell_true(self):
        assert_blocked(
            "import subprocess\nsubprocess.run('ls', shell=True)\nresult = 1",
            "forbidden"  # caught by either import check or shell=True pattern
        )

    def test_syntax_error_in_code(self):
        assert_blocked(
            "result = con.sql('SELECT * FROM df'\n",  # unclosed paren
            "syntax error"
        )