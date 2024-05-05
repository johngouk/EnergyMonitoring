# EnergyMonitoring
A collection of scripts to monitor energy using different monitoring devices

* TuyaEnergyScan.py - interrogates a Tuya Smart 2 Way WiFi Energy Meter Bidirection 1/2 Channel with Clamp App Monitor from AliExpress directly; runs as a systemd daemon with service script
* TuyaEnergyScan.ini - a simple INI file to configure the script, so I can hide my details :-)
* energy-monitor.service - a systemd service config file to put in /etc/systemd/system to run TuyaEnergyScan.py as a service
