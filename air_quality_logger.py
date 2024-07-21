import numpy as np
import paho.mqtt.client as mqtt
import json
import os.path
import sqlite3

HOME = '/home/justin/tmp'
DB_FILE = os.path.join(HOME, 'air_quality_2.db')
sql = '''\
CREATE TABLE IF NOT EXISTS AirQuality 
    (measurement_time DATETIME UNIQUE,
     temperature FLOAT,
     pressure FLOAT,
     humidity FLOAT,
     co2 FLOAT,
     nox FLOAT,
     voc FLOAT,
     aqi_voc,
     aqi_nox,
     pm1 FLOAT,
     pm10 FLOAT,
     pm25 FLOAT,
     lux FLOAT)
'''
db = sqlite3.connect(DB_FILE)
db.execute(sql)

# MQTT settings
MQTT_BROKER = "192.168.86.153"

MQTT_PORT = 1883
MQTT_TOPIC = "airquality/airquality_3_A4BB24/state"

# Data storage
def insert(line):
    db = sqlite3.connect(DB_FILE)
    values = f'("{line[0]:s}",{",".join(map(str, line[1:]))})'
    sql = f'''\
INSERT INTO AirQuality 
VALUES {values}
'''
    try:
        db.execute(sql)
        db.commit()
    except sqlite3.IntegrityError:
        pass
    sql = f'''\
SELECT count(*) 
FROM AirQuality 
WHERE measurement_time == "{line[0]}"
'''
    c = db.execute(sql)
    count = c.fetchone()[0]
    assert count == 1

# MQTT on_message callback
columns = [['datetime', 'Zulu', None, None],
           ['temperature', '$^\circ$F',(60, 80), 0],
           ['pressure', 'KPa', (101, 102), 1],
           ['humidity', '%', (35, 45), 2],
           ['co2', 'PPM', (300, 1500), 3],
           ['nox', '?', (10000, 20000), 5],
           ['voc', '?', (0, 100), 6],
           ['aqi_voc', '?', (0, 200), 7],
           ['aqi_nox', '?', (0, 200), 7],
           ['pm1', '?', (0, 200), 7],
           ['pm10', '?', (0, 200), 7],
           ['pm25', '?', (0, 200), 7],
           ['lux', '-', (0, 1000), 4]]

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        # Assuming data has fields 'timestamp' and 'air_quality'
        timestamp = np.datetime64("now", 's')
        
        line = [timestamp] + [data[c[0]] for c in columns[1:]]
        line[1] = line[1] * 9/5 + 32
        line[2] /= 1000.
        print(','.join(map(str, line)))
        insert(line)
        
    except Exception as e:
        print(f"Error processing message: {e}")
        raise
# MQTT client setup
client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.subscribe(MQTT_TOPIC)
client.loop_start()
try:
    while True:
        pass
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
    print("Disconnected from MQTT broker.")
