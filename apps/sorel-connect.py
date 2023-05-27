import appdaemon.plugins.hass.hassapi as hass
import requests
from typing import Final

SENSOR_RESORUCE: Final[str] = "sensors.json"
SENSOR_COUNT: Final[int] = 13
RELAY_RESORUCE: Final[str] = "relays.json"
RELAY_COUNT: Final[int] = 7
LOG_RESORUCE: Final[str] = "log.json"
LOG_COUNT: Final[int] = 3


class SorelConnect(hass.Hass):
    def initialize(self):
        self.run_minutely(self.get_data_from_sorel_connect)

    def get_data_from_sorel_connect(self):
        url = self.args["sorel-connect-url"]
        user = self.args["sorel-connect-user"]
        password = self.args["sorel-connect-password"]

        session = requests.session()
        # https://db7bb5.sorel-connect.net/nabto/hosted_plugin/login/execute?email=r.horsmar@arcor.de&password=asdasda&callback=jQuery1102038743513531490015_1685218651224&_=1685218651225
        session.get(
            f"{url}/nabto/hosted_plugin/login/execute?email={user}&password={password}"
        )
