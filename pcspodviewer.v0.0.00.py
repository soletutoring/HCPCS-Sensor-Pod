#!/usr/bin/env python3
#PCSpod datalogger program
#version 0.0.01
#created 6/16/2024

import spidev
import time
from datetime import datetime, timedelta
import sqlite3
import os
import socket

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

# Try to get the hostname from the environment variable
SPOD = os.getenv('HOSTNAME')

# Get PCSpod serial number from the USER environment variable
if not SPOD or SPOD == 'unknown_user':
    SPOD = socket.gethostname()

try:
    while True:
        # Get current UTC time
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

        # Print the record to the console (optional)
        record = f"{SPOD}, utc_{utc_time_str}, cst_{cst_time_str}," + ",".join([f"CH{ch}: {reading}mV" for ch, reading in enumerate(readings)] + [f"ADC{ch}: {adc_count}" for ch, adc_count in enumerate(adc_counts)])
        print(record)
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    # Close the database connection when the script is stopped
    conn.close()