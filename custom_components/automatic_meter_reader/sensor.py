import os
import cv2
import logging
import urllib.request
import voluptuous as vol
from shutil import copyfile
from time import sleep, time
from datetime import timedelta, datetime

from automatic_meter_reader import AutomaticMeterReader

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import PLATFORM_SCHEMA, STATE_CLASS_TOTAL
from homeassistant.const import CONF_NAME, CONF_UNIT_OF_MEASUREMENT, CONF_DEVICE_CLASS

_LOGGER = logging.getLogger(__name__)

CONF_CAMERA_MODEL = "camera_model"
CONF_METER_MODEL = "meter_model"
CONF_IMAGE_URL = "image_url"
CONF_CAPTURE_SERVICE = "capture_service"

def setup_platform(hass, config, add_entities, discovery_info=None):
    _LOGGER.info(str(config))
    add_entities([UtilityMeter(config)])

SCAN_INTERVAL = timedelta(minutes=10)
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_UNIT_OF_MEASUREMENT, default="m³"): cv.string,
        vol.Required(CONF_DEVICE_CLASS, default="water"): cv.string,
        vol.Required(CONF_CAMERA_MODEL): cv.string,
        vol.Required(CONF_METER_MODEL): cv.string,
        vol.Required(CONF_IMAGE_URL): cv.string,
        vol.Required(CONF_CAPTURE_SERVICE): cv.string,
    }
)

class UtilityMeter(SensorEntity):

    def __init__(self, config):
        self._state = None
        self._name = config[CONF_NAME]
        self._unit_of_measurement = config[CONF_UNIT_OF_MEASUREMENT]
        self._device_class = config[CONF_DEVICE_CLASS]
        self._image_url = config[CONF_IMAGE_URL]
        self._cature_service = config[CONF_CAPTURE_SERVICE]
        self._amr = AutomaticMeterReader(config[CONF_CAMERA_MODEL], config[CONF_METER_MODEL])

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    @property
    def force_update(self):
        return True

    @property
    def state_class(self):
        return STATE_CLASS_TOTAL

    @property
    def device_class(self):
        return self._device_class

    def update(self):
        _LOGGER.info("Utility meter update (%s)..." % (self._name))
        output_path = os.path.join(self.hass.config.path(), "automatic_meter_readings", self._name)
        _LOGGER.info("Output path: %s" % (output_path))
        if not os.path.isdir(output_path):
            os.makedirs(output_path, exist_ok=True)

        # Get new image
        _LOGGER.info("Take image...")
        service_component, service_name = self._cature_service.split(".")
        self.hass.services.call(service_component, service_name,
            {"flash_duration_ms": 3000, "flash_intensity": 25},
            blocking=True,
        )

        # Sleep
        _LOGGER.info("Sleep...")
        sleep(5.0)

        # Download
        _LOGGER.info("Download(%s)..." % (self._image_url))
        stamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(output_path, "%s_%s.jpg" % (self._name, stamp_str))
        timer_start = time()
        with urllib.request.urlopen(self._image_url) as r:
            img = r.read()
        _LOGGER.info("Image (%d) downloaded in %.3fs" % (len(img), time() - timer_start))

        # Save
        timer_start = time()
        with open(output_file, "wb") as f:
            f.write(img)
        _LOGGER.info("Save image done in %.3fs" % (time() - timer_start))

        # Get reading
        timer_start = time()
        img = cv2.imread(output_file)
        _LOGGER.info("Imread done in %.3fs" % (time() - timer_start))

        # Readout
        timer_start = time()
        self._amr.readout(img)
        _LOGGER.info("Readout done in %.3fs" % (time() - timer_start))

        # Write debug image
        timer_start = time()
        debug_path = os.path.join(self.hass.config.path(), "www")
        if not os.path.isdir(debug_path):
            os.makedirs(debug_path, exist_ok=True)
        output_debug_file = os.path.join(debug_path, "%s.jpg" % (self._name))
        cv2.imwrite(output_debug_file, self._amr.img_debug, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        _LOGGER.info("Save debug img done in %.3fs" % (time() - timer_start))

        # Update state
        self._state = self._amr.measurement
        _LOGGER.info("Utility meter update done. (%s, %s)" % (self._name, self._amr.measurement))