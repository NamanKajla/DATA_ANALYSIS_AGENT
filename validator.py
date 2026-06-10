import ast


def is_safe_code(code: str) -> tuple[bool, str]:
    """Inspects code syntax constructs to ensure no malicious modules execute."""
    forbidden_imports = {"os", "sys", "subprocess", "shutil", "builtins", "requests", "socket"}

    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_imports:
                        return False, f"Blocked forbidden import: '{alias.name}'"
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in forbidden_imports:
                    return False, f"Blocked forbidden module-level import: '{node.module}'"

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "open", "compile", "globals", "locals"]:
                    return False, f"Blocked system call execution vulnerability: '{node.func.id}'"

        return True, "Passed inspection."
    except SyntaxError as e:
        return False, f"Syntax Verification Failure: {str(e)}"