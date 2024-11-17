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
import subprocess as sp
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
            self.ForecastRequest = datetime.now() + timedelta(minutes=1) # make make a Call every 15 minutes max

            # Set location using domoticz param
            latlon = DomoticzAPI("type=command&param=getsettings")
            if latlon:
                self.lat = str(latlon['Location']['Latitude'])
                self.lon = str(latlon['Location']['Longitude'])
                Domoticz.Debug("Setting lat {} at and lon at {}".format(str(self.lat), str(self.lon)))
                # Set PV Plant
                #DECLINATION = '45'  # Example declination
                #AZIMUTH = '70'  # Example azimuth
                #KWP = '8'  # Example kWp

                # Set PVPlant
                self.PVPlant()
                # Check new forecast
                self.CheckForecast()

                # Updating devices values
                Domoticz.Log("Updating Devices from Solar Forecast datas")
                # Devices[1].Update(nValue=0, sValue="Actuellement : {}".format(str(self.ProdType)))
                # Devices[2].Update(nValue=0, sValue="Aujourdhui : {}".format(str(self.J0Message)))

    def PVPlant(self):

        #LATITUDE = '41.57387'  # Example latitude
        LATITUDE = str(self.lat)
        #LONGITUDE = '2.48982'  # Example longitude
        LONGITUDE = str(self.lon)
        DECLINATION = '45'  # Example declination
        AZIMUTH = '70'  # Example azimuth
        KWP = '8'  # Example kWp
        Domoticz.Debug(f"Setting PV PLANT at {LATITUDE} - {LONGITUDE} - {DECLINATION} - {AZIMUTH} - {KWP}")

        with open('/home/domoticz/plugins/solarforecast/PVPlant.py', 'w') as f:
            f.write(f"# PV Plant variables\n")
            f.write(f"#\n")
            f.write(f"LATITUDE = '{LATITUDE}'\n")
            f.write(f"LONGITUDE = '{LONGITUDE}'\n")
            f.write(f"DECLINATION = '{DECLINATION}'\n")
            f.write(f"AZIMUTH = '{AZIMUTH}'\n")
            f.write(f"KWP = '{KWP}'\n")
            f.write(f"#---- END\n")
        Domoticz.Debug("PV Plant Setted")

    def CheckForecast(self):

        cmd = 'sudo python3 /home/domoticz/plugins/solarforecast/forecastsolar.py'
        output = sp.getoutput(cmd)
        if output == "Forecast received - datas saved" :
            Domoticz.Debug("Check for forecast : {}".format(output))
        else :
            Domoticz.Error("{}".format(output))

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