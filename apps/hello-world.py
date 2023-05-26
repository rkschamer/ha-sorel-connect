import hassapi as hass

class HelloWorld(hass.Hass):

    def initialize(self):
        self.log("Hello World!")


