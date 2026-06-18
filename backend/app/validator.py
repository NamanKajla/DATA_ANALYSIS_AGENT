import ast
import re
from dataclasses import dataclass

# Modules that must never be imported in sandbox code
FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "builtins",
    "socket", "requests", "httpx", "urllib", "urllib2",
    "ftplib", "smtplib", "telnetlib", "imaplib", "poplib",
    "pickle", "shelve", "marshal",
    "ctypes", "cffi", "mmap",
    "threading", "multiprocessing", "concurrent",
    "importlib", "imp", "pkgutil",
    "pathlib", "glob", "fnmatch",
    "tempfile", "io",
    "signal", "atexit", "gc",
    "inspect", "dis", "tokenize", "ast",
    "pdb", "cProfile", "profile", "tracemalloc",
    "logging",
}

# Function calls that must never appear
FORBIDDEN_CALLS = {
    "eval", "exec", "compile",
    "open", "input",
    "__import__",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "hasattr",
    "type", "isinstance", "issubclass",
    "memoryview", "bytearray",
    "breakpoint",
}

# Attribute access patterns that could escape the sandbox
FORBIDDEN_ATTRIBUTE_CHAINS = [
    # dunder escapes
    r"\b__class__\b", r"\b__base__\b", r"\b__bases__\b",
    r"\b__subclasses__\b", r"\b__mro__\b",
    r"\b__globals__\b", r"\b__builtins__\b",
    r"\b__code__\b", r"\b__func__\b",
    r"\b__wrapped__\b", r"\b__closure__\b",
    r"\b__dict__\b", r"\b__module__\b",
    r"\b__loader__\b", r"\b__spec__\b",
    r"\b__file__\b", r"\b__path__\b",
    # filesystem / shell via string
    r"shell\s*=\s*True",
    r"Popen\s*\(",
]

# Secrets that must never appear in generated code
_SECRET_PATTERNS = [
    re.compile(r"GROQ_API_KEY", re.IGNORECASE),
    re.compile(r"SUPABASE_URL", re.IGNORECASE),
    re.compile(r"SUPABASE_KEY", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),      # OpenAI-style keys
    re.compile(r"eyJ[A-Za-z0-9_\-]{20,}", re.IGNORECASE),   # JWT tokens
    re.compile(r"postgres(?:ql)?://[^\s'\"]+"),               # DB connection strings
    re.compile(r"mysql://[^\s'\"]+"),
]

_MAX_CODE_LENGTH = 8_000   # characters; protects against prompt-injection blobs
_MAX_LOOP_ITER   = 10_000  # rough guard: flag suspiciously large range() literals


@dataclass
class ValidationResult:
    is_safe: bool
    reason: str = ""


def _check_secrets(code: str) -> ValidationResult:
    """Reject code that contains secret values or references to secret env vars."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(code):
            return ValidationResult(False, f"Code contains a sensitive secret or credential pattern: {pattern.pattern!r}")
    return ValidationResult(True)


def _check_length(code: str) -> ValidationResult:
    if len(code) > _MAX_CODE_LENGTH:
        return ValidationResult(False, f"Code exceeds maximum allowed length ({len(code)} > {_MAX_CODE_LENGTH} chars)")
    return ValidationResult(True)


def _check_attribute_chains(code: str) -> ValidationResult:
    for pattern in FORBIDDEN_ATTRIBUTE_CHAINS:
        if re.search(pattern, code):
            return ValidationResult(False, f"Forbidden attribute access detected: {pattern!r}")
    return ValidationResult(True)


def _check_ast(code: str) -> ValidationResult:
    """Walk the AST and block forbidden imports and calls."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ValidationResult(False, f"Syntax error in generated code: {exc}")

    for node in ast.walk(tree):
        # --- import checks ---
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    return ValidationResult(False, f"Forbidden import: '{alias.name}'")

        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    return ValidationResult(False, f"Forbidden module import: '{node.module}'")

        # --- call checks ---
        if isinstance(node, ast.Call):
            func = node.func

            # bare name: eval(...), exec(...)
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                return ValidationResult(False, f"Forbidden function call: '{func.id}()'")

            # attribute call: obj.__class__, obj.system(...)
            if isinstance(func, ast.Attribute):
                if func.attr in FORBIDDEN_CALLS:
                    return ValidationResult(False, f"Forbidden attribute call: '.{func.attr}()'")
                if func.attr.startswith("__") and func.attr.endswith("__"):
                    return ValidationResult(False, f"Forbidden dunder method call: '.{func.attr}()'")

        # --- suspiciously large range literals (rudimentary DoS guard) ---
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "range":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                        if arg.value > _MAX_LOOP_ITER:
                            return ValidationResult(False, f"Suspiciously large range() literal: {arg.value}")

    return ValidationResult(True)


def validate_generated_code(code: str) -> ValidationResult:
    """
    Run all security checks on LLM-generated code before execution.

    Returns a ValidationResult with is_safe=True only if every check passes.
    Checks run in fast-to-slow order so cheap checks short-circuit early.
    """
    for check in (
        _check_length,
        _check_secrets,
        _check_attribute_chains,
        _check_ast,
    ):
        result = check(code)
        if not result.is_safe:
            return result

    return ValidationResult(True, "All checks passed")