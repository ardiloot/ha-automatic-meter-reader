import os
import cv2
import logging
import urllib.request
from shutil import copyfile
from time import sleep, time
from datetime import timedelta, datetime

from cnn_utility_meter_reader import NeuralnetUtilityReader

from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_NAME, CONF_UNIT_OF_MEASUREMENT

CONF_CAMERA_MODEL = "camera_model"
CONF_METER_MODEL = "meter_model"
_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    _LOGGER.info(str(config))
    add_entities([UtilityMeter(config[CONF_NAME], config[CONF_CAMERA_MODEL], config[CONF_METER_MODEL], config[CONF_UNIT_OF_MEASUREMENT])])

SCAN_INTERVAL = timedelta(minutes=10)

class UtilityMeter(Entity):

    def __init__(self, name, camera_model, meter_model, unit_of_measurement):
        _LOGGER.info("Utility meter: %s (camera %s, meter %s, unit %s)" % (name, camera_model, meter_model, unit_of_measurement))
        self._state = None
        self._name = name
        self._unit_of_measurement = unit_of_measurement
        self._ur = NeuralnetUtilityReader(camera_model, meter_model)

    @property
    def name(self):
        return self._name

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def state(self):
        return self._state

    @property
    def force_update(self):
        return True

    def update(self):
        _LOGGER.info("Utility meter update (%s)..." % (self._name))
        output_path = os.path.join(self.hass.config.path(), "utility_meter_readings", self._name)
        _LOGGER.info("Output path: %s" % (output_path))
        if (not os.path.isdir(output_path)):
            os.makedirs(output_path, exist_ok=True)

        # Get new image
        _LOGGER.info("Take image...")
        self.hass.services.call(
            "esphome",
            "cold_water_meter_capture",
            {"flash_duration_ms": 3000, "flash_intensity": 25},
            blocking=True,
        )

        # Sleep
        _LOGGER.info("Sleep...")
        sleep(5.0)

        # Download
        url = "http://192.168.1.165/saved-photo"
        stamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_path, "%s_%s.jpg" % (self._name, stamp_str))
        download_start = time()
        with urllib.request.urlopen(url) as r:
            with open(output_file, "wb") as f:
                img = r.read()
                f.write(img)
        _LOGGER.info("Image (%d) downloaded in %.3fs" % (len(img), time() - download_start))

        # Get reading
        output_debug_file = os.path.join(output_path, "%s_%s_debug.jpg" % (self._name, stamp_str))
        img = cv2.imread(output_file)
        self._ur.readout(img)
        cv2.imwrite(output_debug_file, self._ur.img_debug)

        # Save latest file
        latest_file = os.path.join(self.hass.config.path(), "www", "%s.jpg" % (self._name))
        copyfile(output_debug_file, latest_file)

        # Update state
        self._state = self._ur.measurement
        _LOGGER.info("Utility meter update done. (%s, %s)" % (self._name, self._ur.measurement))