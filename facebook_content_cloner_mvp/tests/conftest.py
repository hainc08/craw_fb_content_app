import os
import sys
import tempfile
from pathlib import Path

os.environ['FBCLONER_HOME'] = tempfile.mkdtemp(prefix='fbcloner_test_')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture
def conn(tmp_path, monkeypatch):
    import app
    monkeypatch.setattr(app, 'DB', tmp_path / 'test.sqlite3')
    app.init_db()
    c = app.db()
    yield c
    c.close()
