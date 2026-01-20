import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from metamatch import strategy_data

if __name__ == "__main__":
    print("🚀 Initializing Master Strategy Cache...")
    data = strategy_data.update_strategy_cache()
    if data:
        print(f"✅ Cache built successfully! Total Pokemon: {len(data)}")
    else:
        print("❌ Failed to build strategy cache.")
