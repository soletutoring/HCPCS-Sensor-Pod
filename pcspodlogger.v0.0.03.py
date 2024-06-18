#!/usr/bin/env python3
# PCSpod datalogger program
# version 0.0.03
# created 6/18/2024

import spidev
import time
from datetime import datetime, timedelta
import sqlite3
import os
import socket
import RPi.GPIO as GPIO
import signal
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure rPi for GPIO pin numbering
GPIO.setmode(GPIO.BOARD)
GPIO.setup(22, GPIO.OUT)

# Ensure the LED is off initially
GPIO.output(22, 0)

# Open SPI bus
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

# Function to handle SPI read
def read_channel(channel):
    try:
        # Perform SPI transaction and store returned bits in 'r'
        r = spi.xfer2([1, (8 + channel) << 4, 0])
        # Extract ADC value from returned bits
        adc_out = ((r[1] & 3) << 8) + r[2]
        return adc_out
    except Exception as e:
        logging.error(f"Error in read_channel: {e}")
        return None

# Function to convert ADC value to millivolts
def convert_millivolts(data, places):
    try:
        # Converts ADC value to voltage
        millivolts = (data * 3300) / 1023  # Adjusted to reflect 3.3V reference
        millivolts = round(millivolts, places)
        return millivolts
    except Exception as e:
        logging.error(f"Error in convert_millivolts: {e}")
        return None

# Function to check recording status
def recordingstatus():
    try:
        c.execute('''select utc_time from sensor_data order by utc_time desc limit 1''')
        cursorobj = c.fetchone()
        if cursorobj:
            lastrecord = datetime.strptime(cursorobj[0], "%Y-%m-%d %H:%M:%S")
        else:
            lastrecord = None

        criteria_raw = datetime.utcnow()
        criteria = criteria_raw - timedelta(seconds=3)

        if lastrecord and lastrecord > criteria:
            GPIO.output(22, 1)  # Status LED is on and recording status is active
            time.sleep(0.1)
            GPIO.output(22, 0)
            #logging.info("Recording status is active")
        else:
            GPIO.output(22, 0)  # Status LED is off and recording status is inactive
            logging.info("Recording status is inactive")
    except Exception as e:
        logging.error(f"An error occurred in recordingstatus: {e}")
        GPIO.output(22, 0)  # Turn off the LED in case of an error

# Connect to the SQLite database (or create it if it doesn't exist)
try:
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
except Exception as e:
    logging.error(f"An error occurred in database setup: {e}")
    sys.exit(1)

# Try to get the hostname from the environment variable
try:
    SPOD = os.getenv('HOSTNAME')

    if not SPOD or SPOD == 'unknown_user':
        SPOD = socket.gethostname()
except Exception as e:
    logging.error(f"An error occurred in getting hostname: {e}")
    SPOD = None

# Function to record data into database
def record():
    try:
        utc_time = datetime.utcnow()
        cst_conversion = utc_time - timedelta(hours=6)
        utc_time_str = utc_time.strftime('%Y-%m-%d %H:%M:%S')
        cst_time_str = cst_conversion.strftime('%Y-%m-%d %H:%M:%S')

        readings = []
        adc_counts = []
        for channel in range(8):
            adc_count = read_channel(channel)
            if adc_count is not None:
                millivolts = convert_millivolts(adc_count, 2)
                if millivolts is not None:
                    readings.append(millivolts)
                    adc_counts.append(adc_count)
                else:
                    logging.warning(f"Failed to convert ADC count for channel {channel}")
            else:
                logging.warning(f"Failed to read ADC count for channel {channel}")

        c.execute('''
        INSERT INTO sensor_data (utc_time, cst_time, SPOD, ch0, ch1, ch2, ch3, ch4, ch5, ch6, ch7, adc0, adc1, adc2, adc3, adc4, adc5, adc6, adc7)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (utc_time_str, cst_time_str, SPOD, *readings, *adc_counts))
        conn.commit()

        record_info = f"{SPOD}, utc_{utc_time_str}, cst_{cst_time_str}," + ",".join(
            [f"CH{ch}: {reading}mV" for ch, reading in enumerate(readings)] +
            [f"ADC{ch}: {adc_count}" for ch, adc_count in enumerate(adc_counts)])
        logging.info(record_info)

    except Exception as e:
        logging.error(f"An error occurred in record function: {e}")

# Set intervals for recording and status checking
interval_record = timedelta(seconds=1)
interval_status = timedelta(seconds=5)

# Initialize variables for time tracking
lastrecord_entry = datetime.utcnow()
lastrecord_status = datetime.utcnow()

# Function to check recording status based on database entries
def checkstatus():
    try:
        utc_current = datetime.utcnow()
        c.execute('''select utc_time from sensor_data order by utc_time desc limit 1''')
        lastrecord_dbqry = c.fetchone()
        if lastrecord_dbqry:
            lastrecord_db = datetime.strptime(lastrecord_dbqry[0], "%Y-%m-%d %H:%M:%S")
        else:
            lastrecord_db = None
        delta_checkstatus = utc_current - lastrecord_db
        if lastrecord_db and delta_checkstatus < interval_status:
            GPIO.output(22, 1)
            #logging.info("Database entry is active")
        else:
            GPIO.output(22, 0)
            #logging.info("Database entry is inactive")
    except Exception as e:
        logging.error(f"An error occurred in checkstatus: {e}")
        GPIO.output(22, 0)

# Function to control the main loop
def control():
    try:
        global lastrecord_entry, lastrecord_status

        utc_current = datetime.utcnow()
        delta_record = utc_current - lastrecord_entry
        delta_status = utc_current - lastrecord_status

        if delta_record > interval_record:
            record()
            lastrecord_entry = utc_current

        if delta_status > interval_status:
            recordingstatus()
            lastrecord_status = utc_current

    except Exception as e:
        logging.error(f"An error occurred in control function: {e}")

# Function to handle cleanup
def cleanup(signal_received, frame):
    logging.info("Cleaning up GPIO and database connections...")
    GPIO.output(22, 0)  # Turn off the LED
    GPIO.cleanup()  # Clean up GPIO settings
    conn.close()  # Close the database connection
    sys.exit(0)  # Exit the script

# Main loop
if __name__ == "__main__":
    try:
        while True:
            control()
            time.sleep(0.1)  # Slight delay to prevent high CPU usage
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected")
    except Exception as e:
        logging.error(f"An error occurred in main loop: {e}")
    finally:
        cleanup(None, None)
