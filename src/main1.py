# MIT License
#
# Copyright (c) 2022  Dr. Magnus Christ (mc0110)
#
# TRUMA-inetbox-simulation
#
# Credentials and MQTT-server-adress must be filled
# If the mqtt-server needs authentification, this can also filled
#
# The communication with the CPplus uses ESP32-UART2 - connect (tx:GPIO17, rx:GPIO16)
#
#
#
# Version: 1.0.1
#
# change_log:
# 0.8.2 HA_autoConfig für den status error_code, clock ergänzt
# 0.8.3 encrypted credentials, including duo_control, improve the MQTT-detection
# 0.8.4 Tested with RP pico w R2040 - only UART-definition must be changed
# 0.8.5 Added support for MPU6050 implementing a 2D-spiritlevel, added board-based autoconfig for UART,
#       added config variables for activating duoControl and spirit-level features 
# 0.8.6 added board-based autoconfig for I2C bus definition
# 1.0.0 web-frontend implementation
# 1.0.1 using mqtt-commands for reboot, ota, OS-run
# 1.5.x chance browser behavior
# 2.0.x chance connect and integrate mqtt-logic


import logging
import uasyncio as asyncio
from tools import set_led
from lin import Lin
from duocontrol import duo_ctrl
from spiritlevel import spirit_level
import time
from machine import UART, Pin, I2C, soft_reset

log = logging.getLogger(__name__)

# define global objects - important for processing
connect = None
lin = None
dc = None
sl = None

# Change the following configs to suit your environment
S_TOPIC_1       = 'service/truma/set/'
S_TOPIC_2       = 'homeassistant/status'
Pub_Prefix      = 'service/truma/control_status/' 
Pub_SL_Prefix   = 'service/spiritlevel/status/'




# Auto-discovery-function of home-assistant (HA)
HA_MODEL  = 'inetbox'
HA_SWV    = 'V03'
HA_STOPIC = 'service/truma/control_status/'
HA_CTOPIC = 'service/truma/set/'

HA_CONFIG = {
    "alive":                ['homeassistant/binary_sensor/truma/alive/config', '{"name": "TRUMA Alive", "unique_id": "truma_alive", "model": "' + HA_MODEL + '", "sw_version": "' + HA_SWV + '", "device_class": "running", "state_topic": "' + HA_STOPIC + 'alive"}'],
    "release":              ['homeassistant/sensor/release/config', '{"name": "TRUMA Release", "unique_id": "truma_release", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'release"}'],
    "current_temp_room":    ['homeassistant/sensor/current_temp_room/config', '{"name": "TRUMA Current Temp Room", "unique_id": "truma_current_temp_room", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "device_class": "temperature", "unit_of_measurement": "°C", "state_topic": "' + HA_STOPIC + 'current_temp_room"}'],
    "current_temp_water":   ['homeassistant/sensor/current_temp_water/config', '{"name": "TRUMA Current Temp Water", "unique_id": "truma_current_temp_water", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "device_class": "temperature", "unit_of_measurement": "°C", "state_topic": "' + HA_STOPIC + 'current_temp_water"}'],
    "target_temp_room":     ['homeassistant/sensor/target_temp_room/config', '{"name": "TRUMA Target Temp Room", "unique_id": "truma_target_temp_room", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "device_class": "temperature", "unit_of_measurement": "°C", "state_topic": "' + HA_STOPIC + 'target_temp_room"}'],
    "target_temp_water":    ['homeassistant/sensor/target_temp_water/config', '{"name": "TRUMA Target Temp Water", "unique_id": "truma_target_temp_water", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "device_class": "temperature", "unit_of_measurement": "°C", "state_topic": "' + HA_STOPIC + 'target_temp_water"}'],
    "energy_mix":           ['homeassistant/sensor/energy_mix/config', '{"name": "TRUMA Energy Mix", "unique_id": "truma_energy_mix", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'energy_mix"}'],
    "el_power_level":       ['homeassistant/sensor/el_level/config', '{"name": "TRUMA Electric Power Level", "unique_id": "truma_el_power_level", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "device_class": "power", "unit_of_measurement": "W", "state_topic": "' + HA_STOPIC + 'el_power_level"}'],
    "heating_mode":         ['homeassistant/sensor/heating_mode/config', '{"name": "TRUMA Heating Mode", "unique_id": "truma_heating_mode", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'heating_mode"}'],
    "operating_status":     ['homeassistant/sensor/operating_status/config', '{"name": "TRUMA Operating Status", "unique_id": "truma_operating_status", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'operating_status"}'],
    "error_code":           ['homeassistant/sensor/error_code/config', '{"name": "TRUMA Error Code", "unique_id": "truma_error_code", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'error_code"}'],
    "clock":                ['homeassistant/sensor/clock/config', '{"name": "TRUMA Clock", "unique_id": "truma_clock", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "state_topic": "' + HA_STOPIC + 'clock"}'],
    "set_target_temp_room": ['homeassistant/select/target_temp_room/config', '{"name": "TRUMA Set Room Temp", "unique_id": "truma_set_roomtemp", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'target_temp_room", "options": ["0", "10", "15", "18", "20", "21", "22"] }'],
    "set_target_temp_water":['homeassistant/select/target_temp_water/config', '{"name": "TRUMA Set Water Temp", "unique_id": "truma_set_warmwater", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'target_temp_water", "options": ["0", "40", "60", "200"] }'],
    "set_heating_mode":     ['homeassistant/select/heating_mode/config', '{"name": "TRUMA Set Heating Mode", "unique_id": "truma_set_heating_mode", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'heating_mode", "options": ["off", "eco", "high"] }'],
    "set_energy_mix":       ['homeassistant/select/energy_mix/config', '{"name": "TRUMA Set Energy Mix", "unique_id", "truma_set_energy_mix", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'energy_mix", "options": ["none", "gas", "electricity", "mix"] }'],
    "set_el_power_level":   ['homeassistant/select/el_power_level/config', '{"name": "TRUMA Set Electrical Power Level", "unique_id": "truma_set_el_power_level", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'el_power_level", "options": ["0", "900", "1800"] }'],
    "set_reboot":           ['homeassistant/select/set_reboot/config', '{"name": "TRUMA Set Reboot", "unique_id": "truma_set_reboot", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'reboot", "options": ["0", "1"] }'],
    "set_os_run":           ['homeassistant/select/set_os_run/config', '{"name": "TRUMA Set OS Run", "unique_id": "truma_set_os_run", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'os_run", "options": ["0", "1"] }'],
    "ota_update":           ['homeassistant/select/ota_update/config', '{"name": "TRUMA Set OTA Update", "unique_id": "truma_ota_update", "model": "' + HA_MODEL + '", "sw_version":"' + HA_SWV + '", "command_topic": "' + HA_CTOPIC + 'ota_update", "options": ["0", "1"] }'],
}



# Universal callback function for all subscriptions
def callback(topic, msg, retained, qos):
    global connect
    log.debug(str(topic)+" "+str(msg))
    topic = str(topic)
    topic = topic[2:-1]
    msg = str(msg)
    msg = msg[2:-1]
    # Command received from broker
    if topic.startswith(S_TOPIC_1):
        topic = topic[len(S_TOPIC_1):]
        if topic == "reboot":
            if msg == "1":
                log.info("reboot device request via mqtt")
                soft_reset()
            return    
        if topic == "os_run":
            if msg == "1":
                log.info("switch to os_run -> AP-access: 192.168.4.1:80")
                connect.run_mode(0)
                soft_reset()
            return    
        if topic == "ota_update":
            if msg == "1":
                log.info("update software via OTA")
                connect.run_mode(3)
                soft_reset()
            return
        log.info("Received command: "+str(topic)+" payload: "+str(msg))
        if topic in lin.app.status.keys():
            log.info("inet-key:"+str(topic)+" value: "+str(msg))
            try:
                lin.app.set_status(topic, msg)
            except Exception as e:
                log.debug(Exception(e))
                # send via mqtt
        elif not(dc == None):
            if topic in dc.status.keys():
                log.info("dc-key:"+str(topic)+" value: "+str(msg))
#                try:
                dc.set_status(topic, msg)
#                except Exception as e:
#                    print(exception(e))
                    # send via mqtt
            else:
                log.debug("key incl. dc is unkown")
        else:
            log.debug("key w/o dc is unkown")
    # HA-server send ONLINE message        
    if (topic == S_TOPIC_2) and (msg == 'online'):
        log.info("Received HOMEASSISTANT-online message")
        await set_ha_autoconfig(connect.client)


# Initialze the subscripted topics
async def conn_callback(client):
    log.debug("Set subscription")
    # inetbox_set_commands
    await connect.client.subscribe(S_TOPIC_1+"#", 1)
    # HA_online_command
    await connect.client.subscribe(S_TOPIC_2, 1)


# HA autodiscovery - delete all entities
async def del_ha_autoconfig(c):
    for i in HA_CONFIG.keys():
        try:
            await c.publish(HA_CONFIG[i][0], "{}", qos=1)
        except:
            log.debug("Publishing error in del_ha_autoconfig")
        
# HA auto discovery: define all auto config entities         
async def set_ha_autoconfig(c):
    global connect
    log.info("set ha_autoconfig")
    for i in HA_CONFIG.keys():
        try:
            await c.publish(HA_CONFIG[i][0], HA_CONFIG[i][1], qos=1)
#            print(i,": [" + HA_CONFIG[i][0] + "payload: " + HA_CONFIG[i][1] + "]")
        except:
            log.debug("Publishing error in set_ha_autoconfig")
    await c.publish(Pub_Prefix + "release", connect.rel_no, qos=1)
            
        

# main publisher-loop
async def main():
    global repo_update
    global connect
    global file
    log.info("main-loop is running")
    set_led("MQTT", False)
    connect.set_mqtt(1)
    await connect.loop_mqtt()
            
    await del_ha_autoconfig(connect.client)
    await set_ha_autoconfig(connect.client)
    
    i = 0
    while True:
        await asyncio.sleep(10) # Update every 10sec
        if file: logging._stream.flush()
        s =lin.app.get_all(True)
        for key in s.keys():
            log.debug(f'publish {key}:{s[key]}')
            try:
                await connect.client.publish(Pub_Prefix+key, str(s[key]), qos=1)
            except:
                log.debug("Error in LIN status publishing")
        if not(dc == None):        
            s = dc.get_all(True)
            for key in s.keys():
                log.debug(f'publish {key}:{s[key]}')
                try:
                    await connect.client.publish(Pub_Prefix+key, str(s[key]), qos=1)
                except:
                    log.debug("Error in duo_ctrl status publishing")
        if not(sl == None):        
            s = sl.get_all()
            for key in s.keys():
                log.debug(f'publish {key}:{s[key]}')
                try:
                    await connect.client.publish(Pub_SL_Prefix+key, str(s[key]), qos=1)
                except:
                    log.debug("Error in spirit_level status publishing")
        i += 1
        if not(i % 6):
            i = 0
            lin.app.status["alive"][1] = True # publish alive-heartbeat every min
            

# major ctrl loop for inetbox-communication
async def lin_loop():
    global lin
    await asyncio.sleep(1) # Delay at begin
    log.info("lin-loop is running")
    while True:
        lin.loop_serial()
        if not(lin.stop_async): # full performance to send buffer
            await asyncio.sleep_ms(1)


# major ctrl loop for duo_ctrl_check
async def dc_loop():
    await asyncio.sleep(30) # Delay at begin
    log.info("duo_ctrl-loop is running")
    while True:
        dc.loop()
        await asyncio.sleep(10)

async def sl_loop():
    await asyncio.sleep(5) # Delay at begin
    log.info("spirit-level-loop is running")
    while True:
        sl.loop()
        #print("Angle X: " + str(sl.get_roll()) + "      Angle Y: " +str(sl.get_pitch()) )
        await asyncio.sleep_ms(100)


def run(w, lin_debug, inet_debug, mqtt_debug, logfile):
    global connect
    global lin
    global dc
    global sl
    global file
    connect = w
    
    file = logfile
    cred = connect.read_json_creds()
    activate_duoControl  = (cred["ADC"] == "1")
    activate_spiritlevel = (cred["ASL"] == "1")
        
    if mqtt_debug:
        log.setLevel(logging.DEBUG)
    else:    
        log.setLevel(logging.INFO)
        
    if lin_debug: log.info("LIN-LOG defined")
    if inet_debug: log.info("INET-LOG defined")
    if mqtt_debug: log.info("MQTT-LOG defined")
    
    # hw-specific configuration
    # if ("ESP32" in uos.uname().machine):
    if (connect.platform == "esp32"):
        
        log.info("Found ESP32 Board, using UART2 for LIN on GPIO 16(rx), 17(tx)")
        # ESP32-specific hw-UART (#2)
        serial = UART(2, baudrate=9600, bits=8, parity=None, stop=1, timeout=3) # this is the HW-UART-no 2
        if activate_duoControl:
            log.info("Activate duoControl set to true, using GPIO 18,19 as input, 22,23 as output")
        if activate_spiritlevel:
            log.info("Activate spirit_level set to true, using I2C- on GPIO 25(scl), 26(sda)")
            # Initialize the i2c and spirit-level Object
            i2c = I2C(1, sda=Pin(26), scl=Pin(25), freq=400000)
            time.sleep(1.5)
            sl = spirit_level(i2c)
        else:
            sl = None
    elif (connect.platform == "rp2"):
        # RP2 pico w -specific hw-UART (#2)
        log.info("Found Raspberry Pico Board, using UART1 for LIN on GPIO 4(tx), 5(rx)")
        serial = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5), timeout=3) # this is the HW-UART1 in RP2 pico w
        if activate_duoControl:
            log.info("Activate duoControl set to true, using GPIO 18,19 as input, 22,23 as output")
        if activate_spiritlevel:
            log.info("Activate spirit_level set to true, using I2C-1 on GPIO 3(scl), 2(sda)")
            # Initialize the i2c and spirit-level Object
            i2c = I2C(1, sda=Pin(2), scl=Pin(3), freq=400000)
            time.sleep(1.5)
            sl = spirit_level(i2c)
        else:
            sl = None
    else:
        log.debug("No compatible Board found!")
        
    # Initialize the lin-object
    lin = Lin(serial, lin_debug, inet_debug)
    if activate_duoControl:
        # Initialize the duo-ctrl-object
        dc = duo_ctrl()
    else:
        dc = None

    connect.config.set_last_will("service/truma/control_status/alive", "OFF", retain=True, qos=0)  # last will is important
    connect.set_proc(subscript = callback, connect = conn_callback)
#    connect.config.subs_cb = callback
#    connect.config.connect_coro = conn_callback

    if not(dc == None):
        HA_CONFIG.update(dc.HA_DC_CONFIG)
    if not(sl == None):
        HA_CONFIG.update(sl.HA_SL_CONFIG)
        
    loop = asyncio.get_event_loop()
#    client = MQTTClient(config)


    a=asyncio.create_task(main())
    b=asyncio.create_task(lin_loop())
    if not(dc == None):
        c=asyncio.create_task(dc_loop())
    if not(sl == None):
        d=asyncio.create_task(sl_loop())
    loop.run_forever()


