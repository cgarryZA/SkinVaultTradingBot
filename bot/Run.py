import subprocess
import sys

def run(cmd):
    print(f"\n==== Running: {cmd} ====")
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        print(f"ERROR running: {cmd}")
        sys.exit(r.returncode)

run("python GenerateManifest.py")
run("python CreateOrders.py")
run("python GetOrderPrices.py")
print("\nAll scripts executed successfully.")
