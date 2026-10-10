import os
import sys

os.environ["ROUTING"] = "synthetic"
os.environ["GOLDENHOUR_DB"] = ":memory:"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    c = TestClient(app)
    c.post("/api/reset")
    yield c
    c.post("/api/reset")
