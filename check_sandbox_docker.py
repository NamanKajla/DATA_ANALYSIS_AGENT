import os
import subprocess
import tempfile
import shutil

# Setup dummy files
temp_workspace = tempfile.mkdtemp()
data_dir = os.path.join(temp_workspace, "data")
output_dir = os.path.join(temp_workspace, "output")
os.makedirs(data_dir)
os.makedirs(output_dir)

# Create dummy csv
with open(os.path.join(data_dir, "dataset.csv"), "w") as f:
    f.write("ColA,ColB\n1,2\n3,4\n")

# Create dummy user code
with open(os.path.join(temp_workspace, "user_code.py"), "w") as f:
    f.write("result = 42\n")

# Command
cmd = [
    "docker", "run", "--rm",
    "-v", f"{os.path.abspath(os.path.join(temp_workspace, 'user_code.py'))}:/sandbox/user_code.py:ro",
    "-v", f"{os.path.abspath(data_dir)}:/sandbox/data:ro",
    "-v", f"{os.path.abspath(output_dir)}:/sandbox/output",
    "data-agent-sandbox:latest"
]

print("Executing command:", " ".join(cmd))
res = subprocess.run(cmd, capture_output=True, text=True)
print("RETURN CODE:", res.returncode)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
shutil.rmtree(temp_workspace)
