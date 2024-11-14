#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Ecowatt plugin for Domoticz
# Author: MrErwan,
# Version:    0.0.1: alpha..

"""
<plugin key="RL-SOLARFORECAST" name="Ronelabs - Solar Forecast plugin" author="Ronelabs" version="0.0.2" externallink="https://ronelabs.com">
      <description>
        <h2>Ronelabs's'Solar Forecast plugin for domoticz</h2><br/>
        Easily implement in Domoticz Solar Forecast<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import requests
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import math
import base64
import itertools
import subprocess
import os
from typing import Any

try:
    from Domoticz import Devices, Images, Parameters, Settings
except ImportError:
    pass

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue


class BasePlugin:

    def __init__(self):

        self.debug = False
        self.ForecastRequest = datetime.now()
        self.lat = "0"
        self.lon = "0"
        return


    def onStart(self):

        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="Total Today", Unit=1, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "0"))  # default is 0 Kwh forecast
        if 2 not in Devices:
            Domoticz.Device(Name="Total Tomorrow", Unit=2, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "0"))  # default is 0 Kwh forecast

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        #Domoticz.Heartbeat(20)

    def onStop(self):

        Domoticz.Debugging(0)


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

    def onHeartbeat(self):

        Domoticz.Debug("onHeartbeat Called...")

        now = datetime.now()

        if self.ForecastRequest <= now:
            self.ForecastRequest = datetime.now() + timedelta(minutes=1) # make make a Call every 15 minutes

            # Set location using domoticz param
            latlon = DomoticzAPI("type=command&param=getsettings")
            if latlon:
                self.lat = str(latlon['Location']['Latitude'])
                #LATITUDE = self.lat
                self.lon = str(latlon['Location']['Longitude'])
                #LONGITUDE = self.lon
                Domoticz.Debug("Setting lat {} at and lon at {}".format(str(self.lat), str(self.lon)))
                # Set PV Plant
                #DECLINATION = '45'  # Example declination
                #AZIMUTH = '70'  # Example azimuth
                #KWP = '8'  # Example kWp

            """url = f"https://api.forecast.solar/estimate/{LATITUDE}/{LONGITUDE}/{DECLINATION}/{AZIMUTH}/{KWP}?format=key-value&no_sun=1"  # free mode usage

            try:
                Domoticz.Debug("Starting to checking solar forecast")
                # Make the GET request to the Forecast.Solar API
                response = requests.get(url)
                response.raise_for_status()  # Raise an exception for bad status codes

                # Parse the JSON response
                data = response.json()

                # Reseting some variables
                forecastreceived = False

                # Creating a file to save our variables for today
                with open('solar_forecast_variables.py', 'w') as f:
                    f.write(f"# Ronelabs Solar PV Forecast V1.01\n")
                    f.write(f"#\n")

                    # Check forecast reponse for total Wh per day
                    if 'result' in data and 'watt_hours_day' in data['result']:  # Power per hour part
                        forecastreceived = True
                        f.write(f"#------------------------ forecast for total Wh per day\n")
                        for entry in data['result']['watt_hours_day']:
                            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d")
                            hourly_watts = entry['value']
                            # Creating variables
                            now = datetime.now()
                            Today = now.strftime("%d")
                            Timestampday = timestamp.strftime("%d")
                            if Today == Timestampday:  # Forecast is for today
                                variable_name = f"Today-Total-Wh"
                            else:  # Forecast is for tmr
                                variable_name = f"Tomorrow-Total-Wh"
                            # we write directly variable to the file
                            f.write(f"{variable_name} = {hourly_watts}\n")
                        forecastreceived = False
                    else:
                        Domoticz.Error("Unexpected data structure from the API. Check the API response format.")

                    # Check forecast reponse for watt per hour
                    if 'result' in data and 'watts' in data['result']:  # Power per hour part watt_hours_day
                        forecastreceived = True
                        f.write(f"#------------------------ forecast for watts per hours\n")
                        f.write(f"# Today\n")
                        # Reseting some variables
                        firsthourday0 = 0
                        lasthourday0 = 0
                        firsthourday1 = 0
                        lasthourday1 = 0
                        forecastreceivedday = 0
                        for entry in data['result']['watts']:
                            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                            hourly_watts = entry['value']
                            # Creating variables
                            now = datetime.now()
                            Today = now.strftime("%d")
                            Timestampday = timestamp.strftime("%d")
                            tmr = now + timedelta(hours=24)
                            Tomorrow = tmr.strftime("%d")
                            tmrEnd = now + timedelta(hours=48)
                            TomorrowEnd = tmrEnd.strftime("%d")
                            # Ready for checking forecast and creating lines per hour
                            if Today == Timestampday:  # Forecast is for today
                                # Creating todays's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday0 >= startprod:  # We are in prod period
                                        firsthourday0 = 25
                                        break
                                    else:  # We are in period before first hour of prod
                                        f.write(f"Watt-Today-H-{firsthourday0} = 0\n")
                                        firsthourday0 += 1
                                # Creating today's variables for each hour when prod
                                variable_name = f"Watt-Today-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of today's prod
                                lasthourday0 = int(timestamp.hour)
                                forecastreceivedday = 0

                            # elif Tomorrow == Timestampday: # Forecast is for tmr
                            else:  # Forecast is for tmr
                                # Creating todays's variables for each hour after last hour of prod
                                if lasthourday0 < 25:
                                    lasthourday0 += 1
                                    while True:
                                        if lasthourday0 >= 24:
                                            lasthourday0 = 25
                                            f.write(f"# Tomorrow\n")
                                            break
                                        else:
                                            f.write(f"Watt-Today-H-{lasthourday0} = 0\n")
                                            lasthourday0 += 1
                                # Creating tmr's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday1 >= startprod:
                                        firsthourday1 = 25
                                        break
                                    else:
                                        f.write(f"Watt-TMR-H-{firsthourday1} = 0\n")
                                        firsthourday1 += 1
                                # Creating tmr's variables for each hour when prod
                                variable_name = f"Watt-TMR-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of tmr's prod
                                lasthourday1 = int(timestamp.hour)
                                forecastreceivedday = 1

                    else:
                        Domoticz.Error("Unexpected data structure from the API. Check the API response format.")
                    # Creating tmr's variables for each hour after last hour of prod
                    if forecastreceived:
                        if forecastreceivedday == 1:
                            if lasthourday1 < 25:
                                lasthourday1 += 1
                                while True:
                                    if lasthourday1 >= 24:
                                        lasthourday1 = 25
                                        forecastreceived = False
                                        break
                                    else:
                                        f.write(f"Watt-TMR-H-{lasthourday1} = 0\n")
                                        lasthourday1 += 1

                    # Check forecast reponse for Wh per hour
                    if 'result' in data and 'watt_hours_period' in data['result']:  # Power per hour part watt_hours_day
                        forecastreceived = True
                        f.write(f"#------------------------ forecast for Wh per hours\n")
                        f.write(f"# Today\n")
                        # Reseting some variables
                        firsthourday0 = 0
                        lasthourday0 = 0
                        firsthourday1 = 0
                        lasthourday1 = 0
                        forecastreceivedday = 0
                        for entry in data['result']['watt_hours_period']:
                            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                            hourly_watts = entry['value']
                            # Creating variables
                            now = datetime.now()
                            Today = now.strftime("%d")
                            Timestampday = timestamp.strftime("%d")
                            tmr = now + timedelta(hours=24)
                            Tomorrow = tmr.strftime("%d")
                            tmrEnd = now + timedelta(hours=48)
                            TomorrowEnd = tmrEnd.strftime("%d")
                            # Ready for checking forecast and creating lines per hour
                            if Today == Timestampday:  # Forecast is for today
                                # Creating todays's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday0 >= startprod:  # We are in prod period
                                        firsthourday0 = 25
                                        break
                                    else:  # We are in period before first hour of prod
                                        f.write(f"Wh-Today-H-{firsthourday0} = 0\n")
                                        firsthourday0 += 1
                                # Creating today's variables for each hour when prod
                                variable_name = f"Wh-Today-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of today's prod
                                lasthourday0 = int(timestamp.hour)
                                forecastreceivedday = 0

                            # elif Tomorrow == Timestampday: # Forecast is for tmr
                            else:  # Forecast is for tmr
                                # Creating todays's variables for each hour after last hour of prod
                                if lasthourday0 < 25:
                                    lasthourday0 += 1
                                    while True:
                                        if lasthourday0 >= 24:
                                            lasthourday0 = 25
                                            f.write(f"# Tomorrow\n")
                                            break
                                        else:
                                            f.write(f"Wh-Today-H-{lasthourday0} = 0\n")
                                            lasthourday0 += 1
                                # Creating tmr's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday1 >= startprod:
                                        firsthourday1 = 25
                                        break
                                    else:
                                        f.write(f"Wh-TMR-H-{firsthourday1} = 0\n")
                                        firsthourday1 += 1
                                # Creating tmr's variables for each hour when prod
                                variable_name = f"Wh-TMR-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of tmr's prod
                                lasthourday1 = int(timestamp.hour)
                                forecastreceivedday = 1

                    else:
                        Domoticz.Error("Unexpected data structure from the API. Check the API response format.")
                    # Creating tmr's variables for each hour after last hour of prod
                    if forecastreceived:
                        if forecastreceivedday == 1:
                            if lasthourday1 < 25:
                                lasthourday1 += 1
                                while True:
                                    if lasthourday1 >= 24:
                                        lasthourday1 = 25
                                        forecastreceived = False
                                        break
                                    else:
                                        f.write(f"Wh-TMR-H-{lasthourday1} = 0\n")
                                        lasthourday1 += 1

                    # Check forecast reponse for Cumulative Wh per hour
                    if 'result' in data and 'watt_hours' in data['result']:  # Power per hour part watt_hours_day
                        forecastreceived = True
                        f.write(f"#------------------------ forecast for Cumulate Wh per hours\n")
                        f.write(f"# Today\n")
                        # Reseting some variables
                        firsthourday0 = 0
                        lasthourday0 = 0
                        firsthourday1 = 0
                        lasthourday1 = 0
                        forecastreceivedday = 0
                        for entry in data['result']['watt_hours']:
                            timestamp = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                            hourly_watts = entry['value']
                            # Creating variables
                            now = datetime.now()
                            Today = now.strftime("%d")
                            Timestampday = timestamp.strftime("%d")
                            tmr = now + timedelta(hours=24)
                            Tomorrow = tmr.strftime("%d")
                            tmrEnd = now + timedelta(hours=48)
                            TomorrowEnd = tmrEnd.strftime("%d")
                            # Ready for checking forecast and creating lines per hour
                            if Today == Timestampday:  # Forecast is for today
                                # Creating todays's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday0 >= startprod:  # We are in prod period
                                        firsthourday0 = 25
                                        break
                                    else:  # We are in period before first hour of prod
                                        f.write(f"CWh-Today-H-{firsthourday0} = 0\n")
                                        firsthourday0 += 1
                                # Creating today's variables for each hour when prod
                                variable_name = f"CWh-Today-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of today's prod
                                lasthourday0 = int(timestamp.hour)
                                forecastreceivedday = 0

                            # elif Tomorrow == Timestampday: # Forecast is for tmr
                            else:  # Forecast is for tmr
                                # Creating todays's variables for each hour after last hour of prod
                                if lasthourday0 < 25:
                                    lasthourday0 += 1
                                    while True:
                                        if lasthourday0 >= 24:
                                            lasthourday0 = 25
                                            f.write(f"# Tomorrow\n")
                                            break
                                        else:
                                            f.write(f"CWh-Today-H-{lasthourday0} = 0\n")
                                            lasthourday0 += 1
                                # Creating tmr's variables for each hour before first hour of prod
                                startprod = int(timestamp.hour)
                                while True:
                                    if firsthourday1 >= startprod:
                                        firsthourday1 = 25
                                        break
                                    else:
                                        f.write(f"CWh-TMR-H-{firsthourday1} = 0\n")
                                        firsthourday1 += 1
                                # Creating tmr's variables for each hour when prod
                                variable_name = f"CWh-TMR-H-{timestamp.hour}"
                                # we write directly variable to the file
                                f.write(f"{variable_name} = {hourly_watts}\n")
                                # we fix last hour of tmr's prod
                                lasthourday1 = int(timestamp.hour)
                                forecastreceivedday = 1

                    else:
                        Domoticz.Error("Unexpected data structure from the API. Check the API response format.")
                    # Creating tmr's variables for each hour after last hour of prod
                    if forecastreceived:
                        if forecastreceivedday == 1:
                            if lasthourday1 < 25:
                                lasthourday1 += 1
                                while True:
                                    if lasthourday1 >= 24:
                                        lasthourday1 = 25
                                        forecastreceived = False
                                        break
                                    else:
                                        f.write(f"CWh-TMR-H-{lasthourday1} = 0\n")
                                        lasthourday1 += 1

                    f.write(f"#------------------------ END\n")

                Domoticz.Debug("---> ALL OK - Variables have been created and saved to 'solar_forecast_variables.py'")

            except requests.RequestException as e:
                Domoticz.Error(f"API request failed: {e}")
            except ValueError as ve:
                Domoticz.Error(f"Failed to decode JSON response: {ve}")
"""


            Domoticz.Debug("New Forecast received.")

                #Updating devices values
                Domoticz.Log("Updating Devices from Solar Forecast datas")
                #Devices[1].Update(nValue=0, sValue="Actuellement : {}".format(str(self.ProdType)))
                #Devices[2].Update(nValue=0, sValue="Aujourdhui : {}".format(str(self.J0Message)))



global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):
    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
            listvals.append(val)
        except ValueError:
            try:
                val = float(value)
                listvals.append(val)
            except ValueError:
                Domoticz.Error(f"Skipping non-numeric value: {value}")
    return listvals

def CheckParam(name, value, default):

    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param

def DomoticzAPI(APICall):

    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=')}"
    try:
        Domoticz.Debug(f"Domoticz API request: {url}")
        req = request.Request(url)
        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson.get("status") != "OK":
                Domoticz.Error(f"Domoticz API returned an error: status = {resultJson.get('status')}")
                resultJson = None
        else:
            Domoticz.Error(f"Domoticz API: HTTP error = {response.status}")
    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")
    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")
    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")
    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return