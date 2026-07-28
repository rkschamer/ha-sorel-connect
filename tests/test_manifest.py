import json
from pathlib import Path

from custom_components.sorel_connect.const import DOMAIN

MANIFEST = Path("custom_components/sorel_connect/manifest.json")


def test_manifest_domain_matches_const():
    data = json.loads(MANIFEST.read_text())
    assert data["domain"] == DOMAIN
    assert data["config_flow"] is True
    assert data["iot_class"] == "local_polling"
