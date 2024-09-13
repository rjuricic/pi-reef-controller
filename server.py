# Raspberry Pi Relay Controller

from __future__ import print_function

import sys
import time
import json

from flask import Flask
from flask import make_response
from flask import render_template
from flask_bootstrap import Bootstrap
from flask import request, jsonify
from smbus2 import SMBus
import datetime
import threading
import json


from relay_lib import *

error_msg = '{msg:"error"}'
success_msg = '{msg:"success"}'

# Update the following list/tuple with the port numbers assigned to your relay board
PORTS = (16, 18, 7, 11, 13, 15, 19, 21, 23, 27, 29, 31, 33, 35, 40, 38)
NUM_RELAY_PORTS = len(PORTS)

RELAY_NAME = 'AstroBox Relay Controller'

# initialize the relay library with the system's port configuration
if init_relay(PORTS):
    # turn all of the relays off, so we're starting with a clean slate.
    relay_all_off()
else:
    print("Port configuration error")
    # exit the application
    sys.exit(0)

app = Flask(__name__)

bootstrap = Bootstrap(app)

root_dir = '/home/pi/pi-relay-controller'
with open('{}/channels.json'.format(root_dir)) as json_file:
    channel_config = json.load(json_file)

supported_channels = []
for channel in channel_config['channels']:
    if channel['active'] == 'true':
        print('channel: ', channel['channel'])
        supported_channels.append(PORTS[channel['channel'] - 1])
    else:
        relay_off(channel['channel'])

print(supported_channels)

light_channels = []
for channel in channel_config['channels']:
    if channel['light'] == 'true':
        print('channel: ', channel['channel'])
        supported_channels.append(PORTS[channel['channel'] - 1])
print(light_channels)

def read_time():
    with SMBus(1) as bus:
        bus.write_byte(0x68, 0)
        data = bus.read_i2c_block_data(0x68, 0, 7)
        seconds = data[0] & 0x7F
        minutes = data[1] & 0x7F
        hours = data[2] & 0x3F
        current_time = datetime.datetime(
            year=2000 + data[6],
            month=data[5],
            day=data[4],
            hour=hours,
            minute=minutes,
            second=seconds
        )
        return current_time.strftime("%Y-%m-%d %H:%M:%S")

def control_relays():
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        for channel in channel_config['channels']:
            if channel.get('use_schedule'):
                if now == channel.get('on_time'):
                    relay_on(channel['channel'])
                elif now == channel.get('off_time'):
                    relay_off(channel['channel'])
        time.sleep(60)  # Check every minute

# Start the control relays thread
control_thread = threading.Thread(target=control_relays)
control_thread.start()


@app.route('/')
def index():
    print("Loading app Main page")
    return render_template('index.html', relay_name=RELAY_NAME, channel_info=channel_config['channels'])


@app.route('/current_time')
def current_time():
    time_str = read_time()
    return jsonify({"time": time_str})

@app.route('/save_schedule', methods=['POST'])
def save_schedule():
    global channel_config
    schedule = request.json['schedule']
    for ch in schedule:
        for chan in channel_config['channels']:
            if chan['channel'] == ch['channel']:
                chan['on_time'] = ch['on_time']
                chan['off_time'] = ch['off_time']
                chan['use_schedule'] = ch['use_schedule']
    with open('{}/channels.json'.format(root_dir), 'w') as json_file:
        json.dump(channel_config, json_file)
    return jsonify({"msg": "Schedule saved successfully"})

@app.route('/update_schedule/<int:channel>', methods=['POST'])
def update_schedule(channel):
    data = request.get_json()
    on_time = data.get('on_time')
    off_time = data.get('off_time')
    use_schedule = data.get('use_schedule')
    
    for ch in channel_config['channels']:
        if ch['channel'] == channel:
            ch['on_time'] = on_time
            ch['off_time'] = off_time
            ch['use_schedule'] = use_schedule
            break
    
    # Save updated configuration to file
    with open(f'{root_dir}/channels.json', 'w') as json_file:
        json.dump(channel_config, json_file, indent=4)
    
    return {'msg': 'success'}



@app.route('/status/<int:relay>')
def api_get_status(relay):
    res = relay_get_port_status(relay)
    if res:
        print("Relay is ON")
        return make_response("1", 200)
    else:
        print("Relay is OFF")
        return make_response("0", 200)


@app.route('/toggle/<int:relay>')
def api_toggle_relay(relay):
    print("Executing api_relay_toggle:", relay)
    relay_toggle_port(relay)
    return make_response(success_msg, 200)


@app.route('/on/<int:relay>')
def api_relay_on(relay):
    print("Executing api_relay_on:", relay)
    if validate_relay(relay):
        print("valid relay")
        relay_on(relay)
        return make_response(success_msg, 200)
    else:
        print("invalid relay")
        return make_response(error_msg, 404)


@app.route('/off/<int:relay>')
def api_relay_off(relay):
    print("Executing api_relay_off:", relay)
    if validate_relay(relay):
        print("valid relay")
        relay_off(relay)
        return make_response(success_msg, 200)
    else:
        print("invalid relay")
        return make_response(error_msg, 404)


@app.route('/all_on/')
def api_relay_all_on():
    print("Executing api_relay_all_on")
    relay_all_on(supported_channels)
    return make_response(success_msg, 200)


@app.route('/all_off/')
def api_all_relay_off():
    print("Executing api_relay_all_off")
    relay_all_off(supported_channels)
    return make_response(success_msg, 200)

@app.route('/light_on/')
def api_all_light_on():
    print("Executing api_relay_all_off")
    relay_all_off(light_channels)
    return make_response(success_msg, 200)

@app.route('/light_off/')
def api_light_on():
    print("Executing api_relay_all_off")
    relay_all_off(light_channels)
    return make_response(success_msg, 200)

@app.route('/reboot/<int:relay>')
def api_relay_reboot(relay, sleep_time=3):
    print("Executing api_relay_reboot:", relay)
    if validate_relay(relay):
        print("valid relay")
        relay_off(relay)
        time.sleep(sleep_time)
        relay_on(relay)
        return make_response(success_msg, 200)
    else:
        print("invalid relay")
        return make_response(error_msg, 404)


@app.errorhandler(404)
def page_not_found(e):
    print("ERROR: 404")
    return render_template('404.html', the_error=e), 404


@app.errorhandler(500)
def internal_server_error(e):
    print("ERROR: 500")
    return render_template('500.html', the_error=e), 500


def validate_relay(relay):
    # Make sure the port falls between 1 and NUM_RELAY_PORTS
    return (relay > 0) and (relay <= NUM_RELAY_PORTS)


if __name__ == "__main__":
    # On the Pi, you need to run the app using this command to make sure it
    # listens for requests outside of the device.
    app.run(host='0.0.0.0', port=80)
    #app.run(host='0.0.0.0', port=5000, debug=True)
