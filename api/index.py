import sys
import os

# Add backend directory to path so all backend modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from server import app  # noqa: F401
