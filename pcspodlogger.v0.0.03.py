#!/usr/bin/env python3
#PCSpod datalogger program
#version 0.0.03
#created 6/18/2024

import spidev
import time
from datetime import datetime, timedelta
import sqlite3 # https://www.digitalocean.com/community/tutorials/how-to-use-the-sqlite3-module-in-python-3
import os
import socket
import RPi.GPIO as GPIO

# Configure rPi for GPIO pin numbering
GPIO.setmode(GPIO.BOARD)
GPIO.setup(22, GPIO.OUT)
# Reminder >>> GPIO.output(22, 1) = On
# Reminder >>> GPIO.output(22, 0) = Off

# Open SPI bus
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

def read_channel(channel):
    # Perform SPI transaction and store returned bits in 'r'
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    # Extract ADC value from returned bits
    adc_out = ((r[1] & 3) << 8) + r[2]
    return adc_out

def convert_millivolts(data, places):
    # Converts ADC value to voltage
    millivolts = (data * 3300) / 1023  # Adjusted to reflect 3.3V reference
    millivolts = round(millivolts, places)
    return millivolts

def recordingstatus(): #Checks that records are being recorded into the database
    # Fetch the last record entered into the sensor_data table and convert format from utc_time to datetime
    c.execute(''' select utc_time from sensor_data order by utc_time desc limit 1 ''')
    cursorobj=c.fetchone()
    if cursorobj:
        lastrecord=datetime.strptime(cursorobj[0], "%Y-%m-%d %H:%M:%S")
    else:
        lastrecord = None

    # Fetch the current time and calculate the time criteria
    criteria_raw = datetime.utcnow()
    criteria = criteria_raw - timedelta(seconds=10)

    # Compare current time to criteria
    if lastrecord and lastrecord > criteria:
        GPIO.output(22, 1) #Status LED is on and recording status is active
    else:
        GPIO.output(22, 0) #Status LED is off and recording status is inactive

# Connect to the SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('/home/CAMP/Program/sensor_data.db')
c = conn.cursor()

# Ensure the sensor_data table exists
c.execute('''
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    SPOD TEXT,
    utc_time TEXT,
    cst_time TEXT,
    ch0 REAL,
    ch1 REAL,
    ch2 REAL,
    ch3 REAL,
    ch4 REAL,
    ch5 REAL,
    ch6 REAL,
    ch7 REAL,
    adc0 INTEGER,
    adc1 INTEGER,
    adc2 INTEGER,
    adc3 INTEGER,
    adc4 INTEGER,
    adc5 INTEGER,
    adc6 INTEGER,
    adc7 INTEGER
)
''')
conn.commit()

# Try to get the hostname from the environment variable
SPOD = os.getenv('HOSTNAME')

# Get PCSpod machine number from the HOSTNAME environment variable
if not SPOD or SPOD == 'unknown_user':
    SPOD = socket.gethostname()

# Define data recording sequence
def record():
    utc_time = datetime.utcnow()

    # Convert UTC time to CST
    cst_conversion = utc_time - timedelta(hours=6)

    # Format times
    utc_time_str = utc_time.strftime('%Y-%m-%d %H:%M:%S')
    cst_time_str = cst_conversion.strftime('%Y-%m-%d %H:%M:%S')

    # Read all 8 channels
    readings = []
    adc_counts = []  # Initialize adc_counts list
    for channel in range(8):
        adc_count = read_channel(channel)
        millivolts = convert_millivolts(adc_count, 2)
        readings.append(millivolts)
        adc_counts.append(adc_count)

    # Insert data into the database
    c.execute('''
    INSERT INTO sensor_data (utc_time, cst_time, SPOD, ch0, ch1, ch2, ch3, ch4, ch5, ch6, ch7, adc0, adc1, adc2, adc3, adc4, adc5, adc6, adc7)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (utc_time_str, cst_time_str, SPOD, *readings, *adc_counts))
    conn.commit()

    # Print the record to the console (optional)
    record = f"{SPOD}, utc_{utc_time_str}, cst_{cst_time_str}," + ",".join([f"CH{ch}: {reading}mV" for ch, reading in enumerate(readings)] + [f"ADC{ch}: {adc_count}" for ch, adc_count in enumerate(adc_counts)])
    print(record)

#sent time interval parameters
interval_record = timedelta(seconds=1)
interval_status = timedelta(seconds=15)

# Set global variables for checkstatus() and control()
lastrecord_entry=datetime.utcnow()
lastrecord_status=datetime.utcnow()
utc_current=datetime.utcnow()

def checkstatus(): #Checks that records are being recorded into the database
    # Update current UTC time to most recent value
    utc_current=datetime.utcnow()
    # Fetch the last record entered into the sensor_data table and convert format from utc_time to datetime
    c.execute(''' select utc_time from sensor_data order by utc_time desc limit 1 ''')
    lastrecord_dbqry=c.fetchone()
    if lastrecord_dbqry:
        lastrecord_db=datetime.strptime(lastrecord_dbqry[0], "%Y-%m-%d %H:%M:%S")
    else:
        lastrecord_db = None
    # Calculate elapsed time value
    delta_checkstatus = utc_current - lastrecord_db
    # Check that the last database record was recorded within the time interval set by interval_status
    if lastrecord_db and delta_checkstatus < interval_status:
        GPIO.output(22, 1) #Status LED is on and recording status is active
        print("database entry is active")
    else:
        GPIO.output(22, 0) #Status LED is off and recording status is inactive
        print("database entry is inactive)")

def control():
    # Grab global variables
    global lastrecord_entry, lastrecord_status, utc_current, interval_record, interval_status
    # Update current UTC time to most recent value
    utc_current=datetime.utcnow()
    # Calculate elapsed time values
    delta_record = utc_current - lastrecord_entry
    delta_status = utc_current - lastrecord_status
    # Logic statements
    if (delta_record > interval_record):
        record()
        lastrecord_entry = utc_current
        #print("last record update:", lastrecord_entry) #this line is for troubleshooting only
    if (datetime.utcnow() - lastrecord_status > interval_status):
        recordingstatus()
        lastrecord_status = utc_current
        #print("last status update:", lastrecord_status) #this line is for troubleshooting only

# Main loop
if __name__ == "__main__":
    try:
        while True:
            control()
    except KeyboardInterrupt:
        GPIO.cleanup()  # Clean up GPIO settings before exit
        conn.close()  # Close the database connection




