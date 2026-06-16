import os
import tempfile
import shutil
import subprocess

temp_workspace = tempfile.mkdtemp(dir="backend/temp_datasets")
data_dir = os.path.join(temp_workspace, "data")
output_dir = os.path.join(temp_workspace, "output")
os.makedirs(data_dir)
os.makedirs(output_dir)

with open(os.path.join(data_dir, "dataset.csv"), "w") as f:
    f.write("ColA,ColB\n1,2\n")

with open(os.path.join(temp_workspace, "user_code.py"), "w") as f:
    f.write("import json\nwith open('/sandbox/output/result.json', 'w') as f:\n    json.dump({'result': 42}, f)\n")

cmd = [
    "docker", "run", "--rm",
    "-v", f"{os.path.abspath(os.path.join(temp_workspace, 'user_code.py'))}:/sandbox/user_code.py:ro",
    "-v", f"{os.path.abspath(data_dir)}:/sandbox/data:ro",
    "-v", f"{os.path.abspath(output_dir)}:/sandbox/output",
    "data-agent-sandbox:latest"
]

print("CMD:", " ".join(cmd))
res = subprocess.run(cmd, capture_output=True, text=True)
print("RC:", res.returncode)
print("OUT:", res.stdout)
print("ERR:", res.stderr)

shutil.rmtree(temp_workspace)
