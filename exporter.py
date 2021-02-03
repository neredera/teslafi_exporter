#!/usr/bin/env python3

import argparse
import distutils.util as util
import json
import time
import os
import logging
import urllib.parse
import requests

import prometheus_client

from prometheus_client.core import (
    InfoMetricFamily, GaugeMetricFamily, CounterMetricFamily, StateSetMetricFamily)

# TODO: Errorhandling, Recovery after errors (e.g. sensor temporary unavailable), error counters
# TODO: Logging for SystemD. More Logging.
# TODO: Own User/Group for Service

PROMETHEUS_NAMESPACE = 'teslafi'

class TeslaFiCollector(object):
    """Collector for sensor data."""

    teslafi_api_token = None
    last_good_data = None

    def __init__(self, teslafi_api_token, registry=prometheus_client.REGISTRY):
        self.teslafi_api_token = teslafi_api_token

        registry.register(self)

    def callTeslafiApi(self, command):
        url = f'https://www.teslafi.com/feed.php?token={urllib.parse.quote_plus(self.teslafi_api_token)}'
        if (not command is None) and (not command==''):
            url += f'&command={urllib.parse.quote_plus(command)}'

        logging.debug(f'Calling API with {url}')

        response = requests.get(url)

        if response.status_code != 200:
            logging.info(f"Error calling TeslaFi API: {response}")
            raise Exception(f"Error calling TeslaFi API: {response}")

        teslafi_data = response.json()

        if "response" in teslafi_data:
            result = ""
            if "result" in teslafi_data["response"]:
                result = teslafi_data["response"]["result"]

            logging.info(f"Unsucessful API response: {result}")
            raise Exception(f"Unsucessful API response: {result}")

        logging.debug(f'API response: {json.dumps(teslafi_data, indent=2)}')

        return teslafi_data

    def getSetData(self, data, data_old, key):
        if data[key] is None or data[key] == '':
            return data_old[key]
        else:
            return data[key]

    def collect(self):
        
        teslafi_data = self.callTeslafiApi(None) # get current data (will be very empty if car is sleeping)
        # values are similar to the Tesla API. See:
        #   https://www.teslaapi.io/vehicles/state-and-settings
        #   https://tesla-api.timdorr.com/vehicle/state

        if teslafi_data["outside_temp"] is None:
            # the data ist not complete, we complete it with older data.
            # normally we have good current data, if not (e.g. restart of exporter) we ask TeslaFi.
            if self.last_good_data is None:
                self.last_good_data = self.callTeslafiApi('lastGoodTemp') # get older data with temperatures
            teslafi_data_old = self.last_good_data
        else:
            teslafi_data_old = teslafi_data
            self.last_good_data = teslafi_data

        metrics = []

        label_keys = [
            'vin',
            'display_name',
            ]
        label_values = [
            self.getSetData(teslafi_data, teslafi_data_old, "vin"),
            self.getSetData(teslafi_data, teslafi_data_old, "display_name"),
            ]

        teslafi_info = InfoMetricFamily(
            PROMETHEUS_NAMESPACE,
            'TeslaFi car info (almost never changing)',
            value={
                'vin': self.getSetData(teslafi_data, teslafi_data_old, "vin"),
                'display_name': self.getSetData(teslafi_data, teslafi_data_old, "display_name"),
                'vehicle_id': self.getSetData(teslafi_data, teslafi_data_old, "vehicle_id"),
                'option_codes': self.getSetData(teslafi_data, teslafi_data_old, "option_codes"),
                'exterior_color': self.getSetData(teslafi_data, teslafi_data_old, "exterior_color"),
                'roof_color': self.getSetData(teslafi_data, teslafi_data_old, "roof_color"),
                'measure': self.getSetData(teslafi_data, teslafi_data_old, "measure"),
                'eu_vehicle': self.getSetData(teslafi_data, teslafi_data_old, "eu_vehicle"),
                'rhd': self.getSetData(teslafi_data, teslafi_data_old, "rhd"),
                'motorized_charge_port': self.getSetData(teslafi_data, teslafi_data_old, "motorized_charge_port"),
                'spoiler_type': self.getSetData(teslafi_data, teslafi_data_old, "spoiler_type"),
                'third_row_seats': self.getSetData(teslafi_data, teslafi_data_old, "third_row_seats"),
                'car_type': self.getSetData(teslafi_data, teslafi_data_old, "car_type"),
                'rear_seat_heaters': self.getSetData(teslafi_data, teslafi_data_old, "rear_seat_heaters"),
                })
        metrics.append(teslafi_info)

        teslafi_status_info = InfoMetricFamily(
            PROMETHEUS_NAMESPACE + '_status',
            'TeslaFi car info (rarely changing)',
            value={
                'vin': self.getSetData(teslafi_data, teslafi_data_old, "vin"),
                'display_name': self.getSetData(teslafi_data, teslafi_data_old, "display_name"),
                'vehicle_name': self.getSetData(teslafi_data, teslafi_data_old, "vehicle_name"),
                'car_version': self.getSetData(teslafi_data, teslafi_data_old, "car_version"),
                'newVersion': self.getSetData(teslafi_data, teslafi_data_old, "newVersion"),
                'wheel_type': self.getSetData(teslafi_data, teslafi_data_old, "wheel_type"),
                'api_version': self.getSetData(teslafi_data, teslafi_data_old, "api_version"),
                })
        metrics.append(teslafi_status_info)

        teslafi_data_id = CounterMetricFamily(
            PROMETHEUS_NAMESPACE + '_data_id',
            'TeslaFi ID of the data record',
            labels=label_keys)
        teslafi_data_id.add_metric(
            labels=label_values, 
            value=self.getSetData(teslafi_data, teslafi_data_old, "data_id"))
        metrics.append(teslafi_data_id)

        teslafi_polling = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_polling',
            'TeslaFi polling (0=false, 1=true)',
            labels=label_keys)
        teslafi_polling.add_metric(
            labels=label_values, 
            value=
                1 if self.getSetData(teslafi_data, teslafi_data_old, "polling")=="True" else 0)
        metrics.append(teslafi_polling)

        teslafi_odometer_meter = CounterMetricFamily(
            PROMETHEUS_NAMESPACE + '_odometer_meter',
            'Odometer in meters',
            labels=label_keys)
        teslafi_odometer_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "odometer"))*1609.344)
        metrics.append(teslafi_odometer_meter)

        teslafi_outside_temperature = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_outside_temperature',
            'Outside temperature in °C',
            labels=label_keys)
        teslafi_outside_temperature.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "outside_temp")))
        metrics.append(teslafi_outside_temperature)

        teslafi_inside_temperature = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_inside_temperature',
            'Inside temperature in °C',
            labels=label_keys)
        teslafi_inside_temperature.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "inside_temp")))
        metrics.append(teslafi_inside_temperature)

        teslafi_driver_set_temperature = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_driver_set_temperature',
            'Driver set temperature in °C',
            labels=label_keys)
        teslafi_driver_set_temperature.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "driver_temp_setting")))
        metrics.append(teslafi_driver_set_temperature)

        teslafi_passenger_set_temperature = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_passenger_set_temperature',
            'Driver set temperature in °C',
            labels=label_keys)
        teslafi_passenger_set_temperature.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "passenger_temp_setting")))
        metrics.append(teslafi_passenger_set_temperature)

        teslafi_fan_status = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_fan_status',
            'HVAC fan status',
            labels=label_keys)
        teslafi_fan_status.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "fan_status")))
        metrics.append(teslafi_fan_status)

        teslafi_battery_level = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_battery_level',
            'Battery level in % SOC',
            labels=label_keys)
        teslafi_battery_level.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "battery_level")))
        metrics.append(teslafi_battery_level)

        teslafi_usable_battery_level = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_usable_battery_level',
            'Useable battery level in % SOC (partially locked e.g. because of battery temperature)',
            labels=label_keys)
        teslafi_usable_battery_level.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "usable_battery_level")))
        metrics.append(teslafi_usable_battery_level)

        teslafi_battery_range_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_battery_range_meter',
            'Rated range in meter',
            labels=label_keys)
        teslafi_battery_range_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "battery_range"))*1609.344)
        metrics.append(teslafi_battery_range_meter)

        teslafi_battery_range_ideal_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_battery_range_ideal_meter',
            'Ideal range in meter',
            labels=label_keys)
        teslafi_battery_range_ideal_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "ideal_battery_range"))*1609.344)
        metrics.append(teslafi_battery_range_ideal_meter)

        teslafi_battery_range_est_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_battery_range_est_meter',
            'Estimated range in meter',
            labels=label_keys)
        teslafi_battery_range_est_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "est_battery_range"))*1609.344)
        metrics.append(teslafi_battery_range_est_meter)

        teslafi_maxRange_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_maxRange_meter',
            'Maximum range in meter',
            labels=label_keys)
        teslafi_maxRange_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "maxRange"))*1609.344)
        metrics.append(teslafi_maxRange_meter)

        teslafi_charge_limit_soc = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_limit_soc',
            'Charge limit in % SOC',
            labels=label_keys)
        teslafi_charge_limit_soc.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_limit_soc")))
        metrics.append(teslafi_charge_limit_soc)

        teslafi_gps_as_of = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_gps_as_of',
            'GPS timestamp',
            labels=label_keys)
        teslafi_gps_as_of.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "gps_as_of")))
        metrics.append(teslafi_gps_as_of)

        teslafi_heading = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_heading',
            'Heading (in degree)',
            labels=label_keys)
        teslafi_heading.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "heading")))
        metrics.append(teslafi_heading)

        teslafi_longitude = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_longitude',
            'Longitude (in degree)',
            labels=label_keys)
        teslafi_longitude.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "longitude")))
        metrics.append(teslafi_longitude)

        teslafi_latitude = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_latitude',
            'Latitude (in degree)',
            labels=label_keys)
        teslafi_latitude.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "latitude")))
        metrics.append(teslafi_latitude)

        teslafi_idleTime = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_idleTime',
            'Idle time in minutes. ToDo: meaning of negative values? Sleep attempt?',
            labels=label_keys)
        teslafi_idleTime.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "idleTime")))
        metrics.append(teslafi_idleTime)

        label_keys_number = list(label_keys)
        label_keys_number.append("state")
        teslafi_number = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_number',
            'Number of state monitored by TeslaFi',
            labels=label_keys_number)
        metrics.append(teslafi_number)

        label_values_number = list(label_values)
        label_values_number.append("idle")
        teslafi_number.add_metric(
            labels=label_values_number, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "idleNumber")))

        label_values_number = list(label_values)
        label_values_number.append("sleep")
        teslafi_number.add_metric(
            labels=label_values_number, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "sleepNumber")))

        label_values_number = list(label_values)
        label_values_number.append("drive")
        teslafi_number.add_metric(
            labels=label_values_number, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "driveNumber")))

        label_values_number = list(label_values)
        label_values_number.append("charge")
        teslafi_number.add_metric(
            labels=label_values_number, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "chargeNumber")))

        teslafi_sentry_mode = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_sentry_mode',
            'Senty mode (0=off, 1=on)',
            labels=label_keys)
        teslafi_sentry_mode.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "sentry_mode")))
        metrics.append(teslafi_sentry_mode)

        teslafi_locked = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_locked',
            'Locked (0=unlocked, 1=locked)',
            labels=label_keys)
        teslafi_locked.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "locked")))
        metrics.append(teslafi_locked)

        teslafi_is_user_present = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_user_present',
            'User present (0=no, 1=yes)',
            labels=label_keys)
        teslafi_is_user_present.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_user_present")))
        metrics.append(teslafi_is_user_present)

        teslafi_in_service = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_in_service',
            'Car in service (0=no, 1=yes)',
            labels=label_keys)
        teslafi_in_service.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "in_service")))
        metrics.append(teslafi_in_service)

        teslafi_center_display_state = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_center_display_state',
            'Center display state (0=off, ?)',
            labels=label_keys)
        teslafi_center_display_state.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "center_display_state")))
        metrics.append(teslafi_center_display_state)

        label_keys_location = list(label_keys)
        label_keys_location.append("location")
        teslafi_door_open = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_door_open',
            'Door state (0=closed, 1=open)',
            labels=label_keys_location)
        metrics.append(teslafi_door_open)

        label_values_location = list(label_values)
        label_values_location.append("front driver")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "df")))

        label_values_location = list(label_values)
        label_values_location.append("rear driver")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "dr")))

        label_values_location = list(label_values)
        label_values_location.append("front passenger")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "pf")))

        label_values_location = list(label_values)
        label_values_location.append("rear passenger")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "pr")))

        label_values_location = list(label_values)
        label_values_location.append("front trunk")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "ft")))

        label_values_location = list(label_values)
        label_values_location.append("rear trunk")
        teslafi_door_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "rt")))

        label_keys_location = list(label_keys)
        label_keys_location.append("location")
        teslafi_window_open = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_window_open',
            'Window state (0=closed, 1=open?)',
            labels=label_keys_location)
        metrics.append(teslafi_window_open)

        label_values_location = list(label_values)
        label_values_location.append("front driver")
        teslafi_window_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "fd_window")))

        label_values_location = list(label_values)
        label_values_location.append("rear driver")
        teslafi_window_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "rd_window")))

        label_values_location = list(label_values)
        label_values_location.append("front passenger")
        teslafi_window_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "fp_window")))

        label_values_location = list(label_values)
        label_values_location.append("rear passenger")
        teslafi_window_open.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "rp_window")))

        label_keys_location = list(label_keys)
        label_keys_location.append("location")
        teslafi_seat_heater = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_seat_heater',
            'Seat heater (0=off, ?)',
            labels=label_keys_location)
        metrics.append(teslafi_seat_heater)

        label_values_location = list(label_values)
        label_values_location.append("front driver")
        teslafi_seat_heater.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "seat_heater_left")))

        label_values_location = list(label_values)
        label_values_location.append("rear driver")
        teslafi_seat_heater.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "seat_heater_rear_left")))

        label_values_location = list(label_values)
        label_values_location.append("front passenger")
        teslafi_seat_heater.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "seat_heater_right")))

        label_values_location = list(label_values)
        label_values_location.append("rear passenger")
        teslafi_seat_heater.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "seat_heater_rear_right")))

        label_values_location = list(label_values)
        label_values_location.append("rear center")
        teslafi_seat_heater.add_metric(
            labels=label_values_location, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "seat_heater_rear_center")))

        teslafi_battery_heater_on = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_battery_heater_on',
            'Battery heater (0=off, 1=on)',
            labels=label_keys)
        teslafi_battery_heater_on.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "battery_heater_on")))
        metrics.append(teslafi_battery_heater_on)

        teslafi_is_front_defroster_on = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_front_defroster_on',
            'Front defroster (0=off, 1=on)',
            labels=label_keys)
        teslafi_is_front_defroster_on.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_front_defroster_on")))
        metrics.append(teslafi_is_front_defroster_on)

        teslafi_is_rear_defroster_on = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_rear_defroster_on',
            'Rear defroster (0=off, 1=on)',
            labels=label_keys)
        teslafi_is_rear_defroster_on.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_rear_defroster_on")))
        metrics.append(teslafi_is_rear_defroster_on)

        teslafi_defrost_mode = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_defrost_mode',
            'Defrost Mode (0=off, 1=on?)',
            labels=label_keys)
        teslafi_defrost_mode.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "defrost_mode")))
        metrics.append(teslafi_defrost_mode)

        teslafi_is_preconditioning = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_preconditioning',
            'Preconditioning (0=off, 1=on)',
            labels=label_keys)
        teslafi_is_preconditioning.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_preconditioning")))
        metrics.append(teslafi_is_preconditioning)

        teslafi_is_auto_conditioning_on = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_auto_conditioning_on',
            'Auto conditioning (0=off, 1=on)',
            labels=label_keys)
        teslafi_is_auto_conditioning_on.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_auto_conditioning_on")))
        metrics.append(teslafi_is_auto_conditioning_on)

        teslafi_is_climate_on = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_is_climate_on',
            'Climate on (0=off, 1=on)',
            labels=label_keys)
        teslafi_is_climate_on.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "is_climate_on")))
        metrics.append(teslafi_is_climate_on)

        teslafi_left_temp_direction = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_left_temp_direction',
            'Left temp direction (?)',
            labels=label_keys)
        teslafi_left_temp_direction.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "left_temp_direction")))
        metrics.append(teslafi_left_temp_direction)

        teslafi_right_temp_direction = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_right_temp_direction',
            'Right temp direction (?)',
            labels=label_keys)
        teslafi_right_temp_direction.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "right_temp_direction")))
        metrics.append(teslafi_right_temp_direction)

        teslafi_charge_port_cold_weather_mode = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_port_cold_weather_mode',
            'Charge port cold weather mode (0=off, 1=on)',
            labels=label_keys)
        teslafi_charge_port_cold_weather_mode.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "charge_port_cold_weather_mode")))
        metrics.append(teslafi_charge_port_cold_weather_mode)

        teslafi_charge_port_door_open = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_port_door_open',
            'Charge port door open (0=off, 1=on)',
            labels=label_keys)
        teslafi_charge_port_door_open.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "charge_port_door_open")))
        metrics.append(teslafi_charge_port_door_open)

        teslafi_time_to_full_charge_seconds = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_time_to_full_charge_seconds',
            'Estimated time to full charge in seconds (granularity about 15 minutes). ToDo: Correct?',
            labels=label_keys)
        teslafi_time_to_full_charge_seconds.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "time_to_full_charge"))*60)
        metrics.append(teslafi_time_to_full_charge_seconds)

        teslafi_charge_current_request_ampere = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_current_request_ampere',
            'Requested charge current in Ampere (per phase)',
            labels=label_keys)
        teslafi_charge_current_request_ampere.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_current_request")))
        metrics.append(teslafi_charge_current_request_ampere)

        teslafi_charge_enable_request = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_enable_request',
            'Charging enabled (if possible)',
            labels=label_keys)
        teslafi_charge_enable_request.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_enable_request")))
        metrics.append(teslafi_charge_enable_request)

        teslafi_charger_power_kw = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charger_power_kw',
            'Charge power in kW',
            labels=label_keys)
        teslafi_charger_power_kw.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charger_power")))
        metrics.append(teslafi_charger_power_kw)

        teslafi_charger_pilot_current_ampere = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charger_pilot_current_ampere',
            'Max current allowed by charger in ampere per phase (ToDo: correct?)',
            labels=label_keys)
        teslafi_charger_pilot_current_ampere.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charger_pilot_current")))
        metrics.append(teslafi_charger_pilot_current_ampere)

        teslafi_charger_actual_current_ampere = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charger_actual_current_ampere',
            'Actual charge current in ampere per phase',
            labels=label_keys)
        teslafi_charger_actual_current_ampere.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charger_actual_current")))
        metrics.append(teslafi_charger_actual_current_ampere)

        teslafi_charge_current_request_max_ampere = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_current_request_max_ampere',
            'Charge current request max in ampere (?)',
            labels=label_keys)
        teslafi_charge_current_request_max_ampere.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_current_request_max")))
        metrics.append(teslafi_charge_current_request_max_ampere)

        teslafi_charge_energy_added_kwh = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_energy_added_kwh',
            'Energy charged since start of current/last charge session in kWh',
            labels=label_keys)
        teslafi_charge_energy_added_kwh.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_energy_added")))
        metrics.append(teslafi_charge_energy_added_kwh)

        teslafi_charge_range_ideal_added_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_range_ideal_added_meter',
            'Ideal range added since start of current/last charge session in meter',
            labels=label_keys)
        teslafi_charge_range_ideal_added_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_miles_added_ideal"))*1609.344)
        metrics.append(teslafi_charge_range_ideal_added_meter)

        teslafi_charge_range_rated_added_meter = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_range_rated_added_meter',
            'Rated range added since start of current/last charge session in meter',
            labels=label_keys)
        teslafi_charge_range_rated_added_meter.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_miles_added_rated"))*1609.344)
        metrics.append(teslafi_charge_range_rated_added_meter)

        teslafi_charge_rate_kmh = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_rate',
            'Charge rate in km/h (ideal? est? rated?)',
            labels=label_keys)
        teslafi_charge_rate_kmh.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charge_rate"))*1.609344)
        metrics.append(teslafi_charge_rate_kmh)

        teslafi_charger_voltage = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_charger_voltage',
            'Charger voltage in Volt',
            labels=label_keys)
        teslafi_charger_voltage.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "charger_voltage")))
        metrics.append(teslafi_charger_voltage)

        teslafi_fast_charger_present = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_fast_charger_present',
            'Fast charger present (0=none, ?)',
            labels=label_keys)
        teslafi_fast_charger_present.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "fast_charger_present")))
        metrics.append(teslafi_fast_charger_present)

        teslafi_trip_charging = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_trip_charging',
            'Trip charging (?)',
            labels=label_keys)
        teslafi_trip_charging.add_metric(
            labels=label_values, 
            value=int(self.getSetData(teslafi_data, teslafi_data_old, "trip_charging")))
        metrics.append(teslafi_trip_charging)

        speed = self.getSetData(teslafi_data, teslafi_data_old, "speed")
        speed = 0.0 if speed is None else float(speed)
        teslafi_speed_kmh = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_speed_kmh',
            'Speed in kmh',
            labels=label_keys)
        teslafi_speed_kmh.add_metric(
            labels=label_values, 
            value=speed*1.609344)
        metrics.append(teslafi_speed_kmh)

        teslafi_power_kw = GaugeMetricFamily(
            PROMETHEUS_NAMESPACE + '_power_kw',
            'Current power use (kW). Negative during regen. ToDo: When active? Only driving?',
            labels=label_keys)
        teslafi_power_kw.add_metric(
            labels=label_values, 
            value=float(self.getSetData(teslafi_data, teslafi_data_old, "power")))
        metrics.append(teslafi_power_kw)

        car_state = self.getSetData(teslafi_data, teslafi_data_old, "carState")
        car_states = {
            'Sleeping': car_state=='Sleeping',
            'Idling': car_state=='Idling'
            }
        if car_states.get(car_state) is None:
            logging.info(f'Unknown/Unexpected carState: {car_state}')
            car_states[car_state] = True
        teslafi_carState = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_carState',
            'Car state',
            labels=label_keys)
        teslafi_carState.add_metric(
            labels=label_values, 
            value=car_states)
        metrics.append(teslafi_carState)

        shift_state = self.getSetData(teslafi_data, teslafi_data_old, "shift_state")
        if shift_state is None: shift_state = "None"
        shift_states = {
            'None': shift_state=='None',
            }
        if shift_states.get(shift_state) is None:
            logging.info(f'Unknown/Unexpected shift_state: {shift_state}')
            shift_states[shift_state] = True
        teslafi_shift_state = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_shift_state',
            'Shift state',
            labels=label_keys)
        teslafi_shift_state.add_metric(
            labels=label_values, 
            value=shift_states)
        metrics.append(teslafi_shift_state)

        charger_phases = self.getSetData(teslafi_data, teslafi_data_old, "charger_phases")
        if charger_phases is None: charger_phases = "None"
        charger_phases_s = {
            'None': charger_phases=='None',
            }
        if charger_phases_s.get(charger_phases) is None:
            logging.info(f'Unknown/Unexpected charger_phases: {charger_phases}')
            charger_phases_s[charger_phases] = True
        teslafi_charger_phases = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_charger_phases',
            'Charger phases',
            labels=label_keys)
        teslafi_charger_phases.add_metric(
            labels=label_values, 
            value=charger_phases_s)
        metrics.append(teslafi_charger_phases)

        api_state = self.getSetData(teslafi_data, teslafi_data_old, "state")
        api_states = {
            'online': api_state=='online',
            'asleep': api_state=='asleep',
            }
        if api_states.get(api_state) is None:
            logging.info(f'Unknown/Unexpected api_state: {api_state}')
            api_states[api_state] = True
        teslafi_api_state = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_api_state',
            'API state',
            labels=label_keys)
        teslafi_api_state.add_metric(
            labels=label_values, 
            value=api_states)
        metrics.append(teslafi_api_state)

        fast_charger_type = self.getSetData(teslafi_data, teslafi_data_old, "fast_charger_type")
        if fast_charger_type is None or fast_charger_type == '' or fast_charger_type == '<invalid>': fast_charger_type='None'
        fast_charger_types = {
            'None': fast_charger_type=='None',
            }
        if fast_charger_types.get(fast_charger_type) is None:
            logging.info(f'Unknown/Unexpected fast_charger_type: {fast_charger_type}')
            fast_charger_types[fast_charger_type] = True
        teslafi_fast_charger_type = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_fast_charger_type',
            'Fast charger type',
            labels=label_keys)
        teslafi_fast_charger_type.add_metric(
            labels=label_values, 
            value=fast_charger_types)
        metrics.append(teslafi_fast_charger_type)

        charge_port_led_color = self.getSetData(teslafi_data, teslafi_data_old, "charge_port_led_color")
        if charge_port_led_color == '': charge_port_led_color='None'
        charge_port_led_colors = {
            'None': charge_port_led_color=='None',
            }
        if charge_port_led_colors.get(charge_port_led_color) is None:
            logging.info(f'Unknown/Unexpected charge_port_led_color: {charge_port_led_color}')
            charge_port_led_colors[charge_port_led_color] = True
        teslafi_charge_port_led_color = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_port_led_color',
            'Charge port LED color',
            labels=label_keys)
        teslafi_charge_port_led_color.add_metric(
            labels=label_values, 
            value=charge_port_led_colors)
        metrics.append(teslafi_charge_port_led_color)

        charge_port_latch = self.getSetData(teslafi_data, teslafi_data_old, "charge_port_latch")
        charge_port_latches = {
            'Engaged': charge_port_latch=='Engaged',
            }
        if charge_port_latches.get(charge_port_latch) is None:
            logging.info(f'Unknown/Unexpected charge_port_latch: {charge_port_latch}')
            charge_port_latches[charge_port_latch] = True
        teslafi_charge_port_latch = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_charge_port_latch',
            'Charge port latch status',
            labels=label_keys)
        teslafi_charge_port_latch.add_metric(
            labels=label_values, 
            value=charge_port_latches)
        metrics.append(teslafi_charge_port_latch)

        charging_state = self.getSetData(teslafi_data, teslafi_data_old, "charging_state")
        charging_states = {
            'Disconnected': charging_state=='Disconnected',
            }
        if charging_states.get(charging_state) is None:
            logging.info(f'Unknown/Unexpected charging_state: {charging_state}')
            charging_states[charging_state] = True
        teslafi_charging_state = StateSetMetricFamily(
            PROMETHEUS_NAMESPACE + '_charging_state',
            'Charging state',
            labels=label_keys)
        teslafi_charging_state.add_metric(
            labels=label_values, 
            value=charging_states)
        metrics.append(teslafi_charging_state)

        return metrics

""" 
        "climate_keeper_mode":"off",
        "charging_state":"Disconnected",
        "newVersionStatus":""
        "conn_charge_cable":"",
        "fast_charger_brand":"",

        "charge_to_max_range":"0",

        "seat_heater_rear_left_back":"",
        "seat_heater_rear_right_back":"",
        "Date":"2021-02-02 14:06:17",
        "calendar_enabled":"1",
        "odometerF":"None",
        "remote_start_enabled":"",
        "color":null,
        "notifications_enabled":"",
        "id":"56310112355665144",
        "id_s":null,
        "user_charge_enable_request":null,
        "managed_charging_start_time":null,
        "battery_current":"",
        "scheduled_charging_pending":"0",
        "charge_limit_soc_min":"50",
        "charge_limit_soc_std":"90",
        "charge_limit_soc_max":"100",
        "not_enough_power_to_heat":null,
        "max_range_charge_counter":"0",
        "managed_charging_active":"0",
        "managed_charging_user_canceled":"0",
        "scheduled_charging_start_time":null,
        "smart_preconditioning":"",
        "gui_charge_rate_units":null,
        "gui_24_hour_time":null,
        "gui_temperature_units":null,
        "gui_range_display":null,
        "gui_distance_units":null,
        "sun_roof_installed":null,
        "remote_start_supported":"1",
        "homelink_nearby":"0",
        "parsed_calendar_supported":"1",
        "remote_start":"0",
        "perf_config":"",
        "valet_mode":"0",
        "calendar_supported":"1",
        "sun_roof_percent_open":"",
        "seat_type":null,
        "autopark_state":"ready",
        "sun_roof_state":"",
        "notifications_supported":"1",
        "autopark_style":null,
        "last_autopark_error":null,
        "autopark_state_v2":null,
        "inside_tempF":"41",
        "driver_temp_settingF":"69",
        "outside_tempF":"41",
        "battery_heater":"",
        "Notes":"TeslaFi Sleep Mode Sleep Attempt - Email Alert Sent",
        "min_avail_temp":"15.0",
        "max_avail_temp":"28.0",
        "valet_pin_needed":null,
        "timestamp":null,
        "side_mirror_heaters":"",
        "wiper_blade_heater":"",
        "steering_wheel_heater":"",
        "elevation":"",
        "temperature":"C",
        "currency":"Sfr",
        "location":"Bahnhof Visp",
        "rangeDisplay":"rated",
 """

if __name__ == '__main__':
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
#    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    PARSER = argparse.ArgumentParser()
    PARSER.add_argument("--port", help="The port where to expose the exporter (default:9998)", default=9998)
    PARSER.add_argument("--teslafi_api_token", help="TeslaFi API Token from https://teslafi.com/api.php")
    ARGS = PARSER.parse_args()

    port = int(ARGS.port)
    teslafi_api_token = str(ARGS.teslafi_api_token)

    logging.info(f'Using TeslaFi API Token: {teslafi_api_token}')

    TESLAFI_COLLECTOR = TeslaFiCollector(teslafi_api_token)

    logging.info("Starting exporter on port {}".format(port))
    prometheus_client.start_http_server(port)

    # sleep indefinitely
    while True:
        time.sleep(60)