#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Ecowatt plugin for Domoticz
# Author: MrErwan,
# Version:    0.0.1: alpha..

"""
<plugin key="RL-SOLARFORECAST" name="Ronelabs - Solar Forecast plugin" author="Ronelabs" version="0.0.2" externallink="https://ronelabs.com">
      <description>
        <h2>Ronelabs's Solar Forecast plugin for domoticz</h2><br/>
        Easily implement in Domoticz Solar Forecast<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Mode1" label="Declinaison (ex:0 is horizontal)" width="50px" required="true" default="35"/>
        <param field="Mode2" label="Azimut (-90=E,0=S,90=W)" width="50px" required="true" default="0"/>
        <param field="Mode3" label="PV Plant Power in Kwc (ex: 6.350)" width="50px" required="true" default="3"/>
        <param field="Mode4" label="System lost in %" width="50px" required="false" default="0"/>
        <param field="Mode5" label="Spec. folder (expert only - keep blank for ronelabs's standard) " width="600px" required="false" default=""/>
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
        self.SpecFolder = ""
        self.lat = "0"
        self.lon = "0"
        self.decli = 0
        self.azimut = 0
        self.pvpower = 0
        self.pvlost = 0
        self.J0TotalValue = 0
        self.J1TotalValue = 0
        self.J0WperHRaw = "waiting for datas"
        self.J1WperHRaw = "waiting for datas"
        self.SFDatavalue = ""
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
            Domoticz.Device(Name="Today", Unit=1, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(1, 0, "0"))  # default is 0 Kwh forecast
        if 2 not in Devices:
            Domoticz.Device(Name="Tomorrow", Unit=2, Type=243, Subtype=31, Options={"Custom": "1;Kwh"}, Used=1).Create()
            devicecreated.append(deviceparam(2, 0, "0"))  # default is 0 Kwh forecast
        if 3 not in Devices:
            Domoticz.Device(Name="D0-W/H-Raw", Unit=3, Type=243, Subtype=19, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, "waiting for datas"))
        if 4 not in Devices:
            Domoticz.Device(Name="D1-W/H-Raw", Unit=4, Type=243, Subtype=19, Used=1).Create()
            devicecreated.append(deviceparam(4, 0, "waiting for datas"))

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue=device.nvalue, sValue=device.svalue)

        # build PV Plant params
        self.decli = Parameters["Mode1"]
        self.azimut = Parameters["Mode2"]
        self.pvpower = Parameters["Mode3"]
        self.pvlost = Parameters["Mode4"]
        self.SpecFolder = Parameters["Mode5"]

        # Set domoticz heartbeat to 20 s (onheattbeat() will be called every 20 )
        Domoticz.Heartbeat(20)

        # Updating devices values
        Devices[1].Update(nValue=0, sValue="{}".format(str(self.J0TotalValue)))
        Devices[2].Update(nValue=0, sValue="{}".format(str(self.J1TotalValue)))
        Devices[3].Update(nValue=0, sValue="{}".format(str(self.J0WperHRaw)))
        Devices[4].Update(nValue=0, sValue="{}".format(str(self.J1WperHRaw)))

    def onStop(self):

        Domoticz.Debugging(0)


    def onCommand(self, Unit, Command, Level, Color):

        Domoticz.Debug("onCommand called for Unit {}: Command '{}', Level: {}".format(Unit, Command, Level))

    def onHeartbeat(self):

        Domoticz.Debug("onHeartbeat Called...")

        now = datetime.now()

        if self.ForecastRequest <= now:
            self.ForecastRequest = datetime.now() + timedelta(minutes=15) # make a Call every 15 minutes max

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
                Domoticz.Debug("Checking fo Solar Forecast datas")
                SFDatas = SolarForecatAPI("")
                if SFDatas :
                    self.SFDatavalue = str(SFDatas)
                if self.SFDatavalue == "error" :
                    Domoticz.Error("jsonFile datas not updated - Value = {}".format(SFDatas))
                    self.ForecastRequest = datetime.now() + timedelta(minutes=30)
                else :
                    # json filde was updated
                    Domoticz.Debug("jsonFile datas = {}".format(SFDatas))
                    # Total wh forecast
                    self.J0TotalValue = float(SFDatas['forecast']['summary-wh-day']['today'])
                    self.J0TotalValue = round(float((self.J0TotalValue/1000)), 3)
                    self.J1TotalValue = float(SFDatas['forecast']['summary-wh-day']['tomorrow'])
                    self.J1TotalValue = round(float((self.J1TotalValue/1000)), 3)
                    # Watts per hour in Raw
                    # today
                    D0H0 = str(SFDatas['forecast']['hourly-watts']['today']["0"])
                    D0H1 = str(SFDatas['forecast']['hourly-watts']['today']["1"])
                    D0H2 = str(SFDatas['forecast']['hourly-watts']['today']["2"])
                    D0H3 = str(SFDatas['forecast']['hourly-watts']['today']["3"])
                    D0H4 = str(SFDatas['forecast']['hourly-watts']['today']["4"])
                    D0H5 = str(SFDatas['forecast']['hourly-watts']['today']["5"])
                    D0H6 = str(SFDatas['forecast']['hourly-watts']['today']["6"])
                    D0H7 = str(SFDatas['forecast']['hourly-watts']['today']["7"])
                    D0H8 = str(SFDatas['forecast']['hourly-watts']['today']["8"])
                    D0H9 = str(SFDatas['forecast']['hourly-watts']['today']["9"])
                    D0H10 = str(SFDatas['forecast']['hourly-watts']['today']["10"])
                    D0H11 = str(SFDatas['forecast']['hourly-watts']['today']["11"])
                    D0H12 = str(SFDatas['forecast']['hourly-watts']['today']["12"])
                    D0H13 = str(SFDatas['forecast']['hourly-watts']['today']["13"])
                    D0H14 = str(SFDatas['forecast']['hourly-watts']['today']["14"])
                    D0H15 = str(SFDatas['forecast']['hourly-watts']['today']["15"])
                    D0H16 = str(SFDatas['forecast']['hourly-watts']['today']["16"])
                    D0H17 = str(SFDatas['forecast']['hourly-watts']['today']["17"])
                    D0H18 = str(SFDatas['forecast']['hourly-watts']['today']["18"])
                    D0H19 = str(SFDatas['forecast']['hourly-watts']['today']["19"])
                    D0H20 = str(SFDatas['forecast']['hourly-watts']['today']["20"])
                    D0H21 = str(SFDatas['forecast']['hourly-watts']['today']["21"])
                    D0H22 = str(SFDatas['forecast']['hourly-watts']['today']["22"])
                    D0H23 = str(SFDatas['forecast']['hourly-watts']['today']["23"])
                    # creating raw data list of value
                    self.J0WperHRaw = f"{D0H0},{D0H1},{D0H2},{D0H3},{D0H4},{D0H5},{D0H6},{D0H7},{D0H8},{D0H9},{D0H10},{D0H11},{D0H12},{D0H13},{D0H14},{D0H15},{D0H16},{D0H17},{D0H18},{D0H19},{D0H20},{D0H21},{D0H22},{D0H23}"
                    #tmr
                    D1H0 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["0"])
                    D1H1 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["1"])
                    D1H2 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["2"])
                    D1H3 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["3"])
                    D1H4 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["4"])
                    D1H5 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["5"])
                    D1H6 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["6"])
                    D1H7 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["7"])
                    D1H8 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["8"])
                    D1H9 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["9"])
                    D1H10 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["10"])
                    D1H11 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["11"])
                    D1H12 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["12"])
                    D1H13 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["13"])
                    D1H14 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["14"])
                    D1H15 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["15"])
                    D1H16 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["16"])
                    D1H17 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["17"])
                    D1H18 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["18"])
                    D1H19 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["19"])
                    D1H20 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["20"])
                    D1H21 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["21"])
                    D1H22 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["22"])
                    D1H23 = str(SFDatas['forecast']['hourly-watts']['tomorrow']["23"])
                    # creating raw data list of value
                    self.J1WperHRaw = f"{D1H0},{D1H1},{D1H2},{D1H3},{D1H4},{D1H5},{D1H6},{D1H7},{D1H8},{D1H9},{D1H10},{D1H11},{D1H12},{D1H13},{D1H14},{D1H15},{D1H16},{D1H17},{D1H18},{D1H19},{D1H20},{D1H21},{D1H22},{D1H23}"

                # Updating devices values
                Domoticz.Log("Updating Devices from Solar Forecast datas")
                Devices[1].Update(nValue=0, sValue="{}".format(str(self.J0TotalValue)))
                Devices[2].Update(nValue=0, sValue="{}".format(str(self.J1TotalValue)))
                Devices[3].Update(nValue=0, sValue="{}".format(str(self.J0WperHRaw)))
                Devices[4].Update(nValue=0, sValue="{}".format(str(self.J1WperHRaw)))

    def PVPlant(self):

        #LATITUDE = '41.57387'  # Example latitude
        LATITUDE = str(self.lat)
        #LONGITUDE = '2.48982'  # Example longitude
        LONGITUDE = str(self.lon)
        #DECLINATION = '45'  # Example declination
        DECLINATION = str(self.decli)
        #AZIMUTH = '70'  # Example azimuth
        AZIMUTH = str(self.azimut)
        #KWP = '8.480'  # Example kWp
        KWP = str(self.pvpower)
        FOLDER = str(self.SpecFolder)
        Domoticz.Debug(f"Setting PV PLANT at {LATITUDE} - {LONGITUDE} - {DECLINATION} - {AZIMUTH} - {KWP}")

        if self.SpecFolder == "" :
            Domoticz.Debug("Using standard Plugin Folder for Setting PV PLANT")
            with open('/home/domoticz/plugins/solarforecast/PVPlant.py', 'w') as f:
                f.write(f"# PV Plant variables\n")
                f.write(f"#\n")
                f.write(f"LATITUDE = '{LATITUDE}'\n")
                f.write(f"LONGITUDE = '{LONGITUDE}'\n")
                f.write(f"DECLINATION = '{DECLINATION}'\n")
                f.write(f"AZIMUTH = '{AZIMUTH}'\n")
                f.write(f"KWP = '{KWP}'\n")
                f.write(f"FOLDER = /home/domoticz/plugins/solarforecast/\n")
                f.write(f"#---- END\n")
            Domoticz.Debug("PV Plant Setted")
        else :
            PluginFolder = str(self.SpecFolder)
            Domoticz.Debug(f"Using special Folder for Setting PV PLANT : {PluginFolder}")
            with open(f'{PluginFolder}PVPlant.py', 'w') as f:
                f.write(f"# PV Plant variables\n")
                f.write(f"#\n")
                f.write(f"LATITUDE = '{LATITUDE}'\n")
                f.write(f"LONGITUDE = '{LONGITUDE}'\n")
                f.write(f"DECLINATION = '{DECLINATION}'\n")
                f.write(f"AZIMUTH = '{AZIMUTH}'\n")
                f.write(f"KWP = '{KWP}'\n")
                f.write(f"FOLDER = '{FOLDER}'\n")
                f.write(f"#---- END\n")
            Domoticz.Debug("PV Plant Setted")

    def CheckForecast(self):

        if self.SpecFolder == "" :
            Domoticz.Debug("Using standard Plugin Folder for json Forecast file")
            cmd = 'sudo python3 /home/domoticz/plugins/solarforecast/forecastsolar.py'
            output = sp.getoutput(cmd)
        else :
            PluginFolder = str(self.SpecFolder)
            Domoticz.Debug(f"Using special Folder json Forecast file : {PluginFolder}")
            cmd = f'sudo python3 {PluginFolder}forecastsolar.py'
            output = sp.getoutput(cmd)
        #cmd = 'sudo python3 /home/domoticz/plugins/solarforecast/forecastsolar.py'
        #output = sp.getoutput(cmd)
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

def SolarForecatAPI(APICall):

    Domoticz.Debug("Solar Forecast local API Called...")
    SFjsonData = None
    jsonFile = "/home/domoticz/plugins/solarforecast/solar_forecast.json"
    # Check for ecowatt datas file
    if not os.path.isfile(jsonFile):
        Domoticz.Error(f"Can't find {jsonFile} file!")
        return
    else:
        Domoticz.Debug(f"Solar Forcast json Solar Forecast file found")
    # Check for ecowatt datas
    with open(jsonFile) as SFStream:
        try:
            SFjsonData = json.load(SFStream)
        except:
            Domoticz.Error(f"Error opening json Solar Forecast file !")
    return SFjsonData

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