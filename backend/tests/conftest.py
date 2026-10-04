import json
from pathlib import Path

import pytest

from mender.config import ROOT, load_services, load_settings
from mender.db import Database
from mender.pipeline import Context
from mender.runners import make_runner

INCIDENTS = ROOT / "fixtures" / "incidents"


def incident(name: str) -> dict:
    return json.loads((INCIDENTS / f"{name}.json").read_text())


@pytest.fixture
def settings(tmp_path):
    return load_settings(db_path=str(tmp_path / "t.db"), runner="replay", price_in=3.0, price_out=15.0, webhook_secret=None, publish=False)


@pytest.fixture
def ctx(settings):
    return Context(settings, Database(settings.db_path), load_services(settings.services_file), make_runner(settings))
