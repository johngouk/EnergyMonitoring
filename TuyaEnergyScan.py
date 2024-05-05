"""
    Programme to retrieve energy information from the Tuya Dual CT clamp device in the Hall cupboard.
    This goes directly to the device using a key obtained from the Tuya cloud, which may all stop working
    on or about the 20th November 2023, since my demo account runs out then.

    The various configuration items are held in an ini file 'TuyaEnergyScan.ini' in the same directory as the
    script. Logging is to a file 'TuyaEnergyScan.log' in the same directory.

    The data is returned as a JSON string, with data categories encoded as numeric strings. I used the
    info on the Tuya app in conjunction with the info from the tinytuya wizard command to decode the data
    function and scaling.

    The data is in a structure under the key "dps" - which is the Tuya name for Data Point Status (I think).
    The strings for the Data Points are retrieved by tinytuya for this display, you only get the numeric IDs
    in the actual data.
    {'dps':
        {	forward_energy_total '1': 4,
            reverse_energy_total '2': 7,
            power_a ‘101': 257,
            '102': 'REVERSE',
            '104': 'FORWARD',
            power_b ‘105': 143,
            energy_forward_a ’106': 0,
            energy_reverse_a '107': 7,
            energy_forward_b '108': 4,
            energy_reverse_a'109': 0,
            power_factor ’110': 9,
            frequency ‘111': 4921,
            voltage ’112': 2467,
            current_a ‘113': 1103,
            current_b ‘114': 452,
            total_power '115': -114,
            '116': 1000,
            '117': 1000,
            '118': 1000,
            '119': 1000,
            '121': 12,
            '122': 1000,
            '123': 1000,
            '124': 1000,
            '125': 1000,
            '127': 1000,
            '128': 1000,
            '129': 10}}

    The programme maps these into another JSON structure using the DP names, rather than IDs,
    along with a units identifier.

    It also generates an EmonCMS-friendly version of the data, which is a simple dictionary of
    names/values, which are sent individually to MQTT as messages under the topic emon/ASHP/<itemName> with
    the value as the message.

    It appears that something hangs after a randon period, which requires restarting this script. I added
    a WatchDog Timer that, if triggered, causes the script to exit with an error. This allows it to run 
    as a systemd service, and be restarted automatically.

    In addition, logging will only be on initial success, and whenever there's an error. Quiet is good.

"""
import argparse
import tinytuya
import datetime
import paho.mqtt.client as mqtt
import json
import time
import logging
import signal
import traceback
import os, sys
import configparser as c

def WDTHandler(signum, frame):
    signame = signal.Signals(signum).name
    logger.error('Signal handler called with signal '+signame+' '+str(signum))
    traceback.print_stack(file=fd)
    fd.flush()
    fd.close()
    exit('WD Timer Expired!')

WDTValue = 60        # WatchDog Timer interval, used for Faulthandler timeout

def WDT(timeout=WDTValue):  # Set/reset the WDT
    # faulthandler.dump_traceback_later(WDTValue, repeat=False, file=fd, exit=False)
    signal.signal(signal.SIGALRM, WDTHandler)
    signal.alarm(timeout)


# __main__

# Map key values to named
names = {
    # "1": {"name": "forward_energy_total", "factor": 0.01, "units": "kWh"},
    # "2": {"name": "reverse_energy_total", "factor": 0.01, "units": "kWh"},
    "101": {"name": "power_a", "factor": 0.1, "units": "W"},
    "105": {"name": "power_b", "factor": 0.1, "units": "W"},
    "106": {"name": "energy_forward_a", "factor": 0.01, "units": "kWh"},
    "107": {"name": "energy_reverse_a", "factor": 0.01, "units": "kWh"},
    "108": {"name": "energy_forward_b", "factor": 0.01, "units": "kWh"},
    "109": {"name": "energy_reverse_b", "factor": 0.01, "units": "kWh"},
    "110": {"name": "power_factor_a", "factor": 0.01, "units": ""},
    "111": {"name": "frequency", "factor": 0.01, "units": "Hz"},
    "112": {"name": "voltage", "factor": 0.1, "units": "V"},
    "113": {"name": "current_a", "factor": 0.001, "units": "A"},
    "114": {"name": "current_b", "factor": 0.001, "units": "A"},
    # "115": {"name": "total_power", "factor": 0.1, "units": "W"},
    "121": {"name": "power_factor_b", "factor": 0.01, "units": ""},
    # '129': {'name':'129', 'factor':1, 'units':'???'}
}


logfile = 'TuyaEnergyScan.log'
configFile = 'TuyaEnergyScan.ini'

# Need to find location of .py script to use that for logfile/config path!
dir = os.path.dirname(sys.argv[0])
#print ('dir is', dir)
logfile = os.path.join(dir, logfile)
#print ('Log at',logfile)
configFile = os.path.join(dir, configFile)
#print ('Conf at',configFile)

# logging.basicConfig(filename=logfile , encoding='utf-8', level=logging.INFO)
logging.basicConfig(filename=logfile, level=logging.INFO,
# logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(name)s:%(levelname)s:%(message)s')

logger = logging.getLogger('TuyaEnergyScan')

config = c.ConfigParser()
config.read(configFile)

tuya_dev_id=config['DEFAULT']['tuya_dev_id']
tuya_address=config['DEFAULT']['tuya_address']  # Or set to 'Auto' to auto-discover IP address
tuya_local_key=config['DEFAULT']['tuya_local_key']  # 'f)=DnYdajV4P=E)h'

fd = open(logfile,mode='a')    # Horrible hack to get dump data into logfile!
sleepTime = 30  # Loop repeat interval; also used for checking ping time in MQTT connection

logger.info('MQTT1 Client Creating...')
mqtt1 = mqtt.Client(protocol=mqtt.MQTTv311)
logger.info('MQTT1 client Connecting...')
mqtt1.connect("server.local", keepalive=sleepTime + 10)
logger.info('MQTT1 client Connected!')
mqtt1.loop_start()  # Mustn't forget this critical action! Starts a  background thread to listen to the MQTT connection

logger.info('MQTT2 Client Creating...')
mqtt2 = mqtt.Client(protocol=mqtt.MQTTv311)
mqtt2.username_pw_set('emonpi', password='emonpimqtt2016')
logger.info('MQTT2 client Connecting...')
# mqtt2.connect("servernew.local", keepalive=sleepTime + 10)
mqtt2.connect("emonpi.local", keepalive=sleepTime + 10)
logger.info('MQTT2 client Connected!')
mqtt2.loop_start()  # Mustn't forget this critical action! Starts a  background thread to listen to the MQTT connection

# Connect to Device
logger.info('Connecting to Device ' + tuya_dev_id + ' at ' + tuya_address)
d = tinytuya.OutletDevice(
    dev_id=tuya_dev_id,
    address=tuya_address,  # Or set to 'Auto' to auto-discover IP address
    local_key=tuya_local_key,  # 'f)=DnYdajV4P=E)h'
    version=3.4,
)

# for item in names:
#     print (item + ':' + str(names[item]))
successfulScan = False
errorState = False
while True:
    WDT()
    # Get Status
    # timeStamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S:%f%z')
    timeStamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
        sep="T", timespec="auto"
    )
    # Was the last scan attempt sucessful? If so, don't announce this one...
    # Are we in an error state (previous scan not successful)? If yes, then tell people about this one
    if not successfulScan or errorState:
        logger.info('Getting Device Status...')
    data = d.status()
    # print (data)
    # print('set_status() result %r' % data)
    if "dps" in data:
        # NO error this time
        errorState = False
        emonData = {}
        jsonData = '{"Time":"' + timeStamp + '","data":{'
        for k, v in names.items():
            # print (str(v) + ':' + str(float(data['dps'][k])*float((k['factor']))))
            # print (str(names[k]['name']) + ':\t' + str(float(data['dps'][k])*float(names[k]['factor'])) + str(names[k]['units']))
            if k in data["dps"]:
                emonData[names[k]["name"]] = float(data["dps"][k]) * float(names[k]["factor"])
                jsonData = (
                    jsonData
                    + '"'
                    + str(names[k]["name"])
                    + '":{"value":'
                    + str(float(data["dps"][k]) * float(names[k]["factor"]))
                    + ',"units":"'
                    + str(names[k]["units"])
                    + '"},'
                )
        jsonData = jsonData.rstrip("{,") + "}}"
        # print(emonData)
        # print (jsonData)
        # payload = json.loads(jsonData)
        # Check for a previous successful scan - if none yet, print success and remember we did...
        if not successfulScan:
            successfulScan = True
            logger.info('Publishing Meter Data...')
        mqtt1.publish('tele/Meter/data', payload=jsonData, qos=0, retain=False)
        for k, v in emonData.items():
            emonTopic = 'emon/ASHP/'+k
            # print(emonTopic + ':' + str(v), end='')
            mqtt2.publish(emonTopic, payload=v, qos=0, retain=False)
    else:
        # Oops, this scan didn't work, so remember for the next successful one
        successfulScan = False
        # Did we already have an error on the previous scan attempt?
        # If not, remember we did, and tell people we had an error...
        # If yes, don't tell everyone again
        if not errorState:
            errorState = True
            logger.error('Scan error: No data returned!')
            logger.error('Data:' + str(data))

    time.sleep(sleepTime)

