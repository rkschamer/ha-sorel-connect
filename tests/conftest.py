import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import appdaemon.plugins.mqtt.mqttapi as mqtt
from appdaemon.models.config.app import AppConfig

# sorel-connect.py has a hyphen in the filename — importlib is required
sys.path.insert(0, str(Path(__file__).parent.parent / "apps"))
loader = importlib.machinery.SourceFileLoader(
    "sorel_connect",
    str(Path(__file__).parent.parent / "apps" / "sorel-connect.py"),
)
sorel_module = loader.load_module()
SorelConnect = sorel_module.SorelConnect


def make_ad_mock() -> MagicMock:
    ad = MagicMock()
    ad.http = None
    ad.logging.get_child.return_value = logging.getLogger("test")
    ad.logging.get_error.return_value = logging.getLogger("test.error")
    return ad


@pytest.fixture
def ad_mock() -> MagicMock:
    return make_ad_mock()


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "name": "SorelConnect",
            "module": "sorel-connect",
            "class": "SorelConnect",
            "sorel-connect-url": "https://test.sorel-connect.net",
            "sorel-connect-user": "user@test.com",
            "sorel-connect-password": "testpass",
        }
    )


@pytest.fixture
def app(ad_mock: MagicMock, app_config: AppConfig) -> SorelConnect:
    instance = object.__new__(SorelConnect)
    mqtt.Mqtt.__init__(instance, ad_mock, app_config)
    # Replace sync_decorator-wrapped runtime methods with mocks
    instance.run_every = MagicMock()
    instance.mqtt_publish = MagicMock()
    instance.is_client_connected = MagicMock(return_value=True)
    instance.log = MagicMock()
    return instance
