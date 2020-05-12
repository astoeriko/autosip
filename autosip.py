import math
import re
import requests
import getpass
import arrow
import logging
import time
import datetime
import argparse
import json


logger = logging.getLogger('autorun-SIP')
logger.setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


DEFAULTS = {
    'psip_mode': '1',
    'sequence_script': '',
    'seq_loop_count': '1',
    'stimulus_plus_p1': '0',
    'stimulus_minus_p2': '0',
    'sense_plus_p3': '0',
    'sense_minus_p4': '0',
    'start_freq': '1000.0',
    'stop_freq': '0.01',
    'n_steps': '51',
    'amplitude': '5.0',
    'settle_time': '1',
    'settle_cycles': '1',
    'integration_time': '5',
    'integration_cycles': '5',
    'resistor_ohm': '1000',
    'loop_count': '1',
    'master_slave_sel': '0',
    'ext_trigger_sel': '0',
    'filename': 'sip_results',
    'comment': 'comment',
    'submit': '1'
}


# The order of parameters matters!
# Use python 3.7 or later!
PARAM_NAMES_v1_0_1 = {
    'stimulus_channel': 'n1',
    'response_channel': 'n2',
    'start_freq': 'v11',
    'stop_freq': 'v12',
    'n_steps': 'v13',
    'amplitude': 'v14',
    'settle_time': 'v21',
    'settle_cycles': 'v22',
    'integration_time': 'v23',
    'integration_cycles': 'v24',
    'resistor_ohm': 'n3',
    'loop_count': 'loop',
    'master_slave_sel': 'msSel',
    'ext_trigger_sel': 'trigSel',
    'filename': 'n4',
    'comment': 'n5',
    'submit': 'submit'
}
PARAM_NAMES_v1_3_1h1 = {
    'psip_mode': 'funcSelectBox',
    'sequence_script': 'sequence_script',
    'seq_loop_count': 'seq_loop_count',
    'stimulus_plus_p1': 'fx_sel1',
    'stimulus_minus_p2': 'fx_sel2',
    'sense_plus_p3': 'fx_sel3',
    'sense_minus_p4': 'fx_sel4',
    'response_channel': 'resp_chan_list',
    'start_freq': 'start_freq',
    'stop_freq': 'stop_freq',
    'n_steps': 'num_steps',
    'amplitude': 'amplitude',
    'settle_time': 'settle_time',
    'settle_cycles': 'settle_cycles',
    'integration_time': 'int_time',
    'integration_cycles': 'int_cycles',
    'resistor_ohm': 'current_resistor',
    'loop_count': 'loop_count',
    'master_slave_sel': 'ms_sel',
    'ext_trigger_sel': 'trig_sel',
    'filename': 'log_prefix',
    'comment': 'user_comment',
    'submit': 'submit'
}

PORTS = {
    "1": 9344,
    "2": 9345,
    "3": 9346,
    "4": 9347,
}


SUBMIT_BUTTON = '<button name="submit" type="submit" value="1"><b>Submit</b>'
CANCEL_BUTTON = '<button name="submit" type="submit" value="0"><b>Cancel</b>'


def get_param_names(version):
    if version == "1.0.1":
        return PARAM_NAMES_v1_0_1
    elif version == "1.3.1h-1":
        return PARAM_NAMES_v1_3_1h1
    else:
        raise ValueError(f"SIP software version {version} is not supported.")


def get_interval(interval_str):
    time_pattern = "([0-2]?[0-9]):([0-5][0-9])"
    match = re.match(time_pattern, interval_str)
    if match is None:
        raise ValueError("Invalid format for time interval.")
    else:
        hour, minutes = (int(g) for g in match.groups())
    return datetime.timedelta(hours=hour, minutes=minutes)


def first_measure_time(interval):
    now = arrow.utcnow()
    next_full_hour = now.ceil('hour')
    diff_to_full_hour = next_full_hour - now
    num_intervals = diff_to_full_hour / interval
    time_to_next_measurement = (num_intervals - math.floor(num_intervals)) * interval
    return now + time_to_next_measurement


def wait_until(target_time):
    now = arrow.utcnow()
    diff = (target_time - now).total_seconds()
    logger.info('Waiting until %s for next measurement' % target_time.isoformat())
    time.sleep(diff)


def prepare_data(basename, stimulus_channel, response_channels, param_names, **params):
    vals = params.copy()
    vals['filename'] = '%s-ch%s-%s' % (
        arrow.utcnow().strftime("%Y%m%dT%H%MZ"),
        stimulus_channel,
        basename)
    vals['stimulus_channel'] = stimulus_channel
    vals['response_channel'] = ','.join(str(i) for i in response_channels)
    return {instrument_name: vals[name]
            for name, instrument_name in param_names.items()}


def check_device_ready(ip, channels, request_kwargs):
    for channel in channels:
        url = 'http://%s:%s' % (ip, PORTS[channel])
        try:
            r = requests.get(url, **request_kwargs)
        except Exception:
            logger.exception('Could not connect to device. Is the IP address correct? '
                             '(It changes at device reboot!)')
            return False
        if not r.ok:
            logger.exception(f'Got error code from device. {r.text}')
            return False
        if not SUBMIT_BUTTON in r.text:
            logger.error('No submit button on device. It may still be busy...')
            return False
    return True


def check_response(r):
    r.raise_for_status()

    text = r.text
    # The retured page from the server contains a cancel button.
    # This is the best indication for success that we know how to get.
    if CANCEL_BUTTON in text:
        return

    # The server seems to be unhappy about the parameters
    if 'ERROR : Web UI Error' in text:
        raise RuntimeError('The server seems to be complaining about the parameters.')

    # The server still shows us the submit button, this isn't right...
    if SUBMIT_BUTTON in text:
        raise RuntimeError('Submitting failed.')

    # No clue how we would get here...
    raise RuntimeError('Bad response from server.')


def measure(data, param_names, args, request_kwargs):
    logger.info('Starting new measurement.')

    if not check_device_ready(args.ip, args.channels, request_kwargs):
        logger.info('Waiting 15 minutes...')
        time.sleep(60 * 15)
        if not check_device_ready(args.ip, args.channels, request_kwargs):
            logger.error('Skipping this measurement.')
            return

    for stimulus_channel, response_channels in args.channels.items():
        url = 'http://%s:%s' % (args.ip, PORTS[stimulus_channel])
        logger.info('Measuring stimulus channel %s at response channels %s.'
                    % (stimulus_channel, response_channels))
        try:
            run_data = prepare_data(
                args.basename, stimulus_channel, response_channels, param_names, **data)
            response = requests.post(url, data=run_data, **request_kwargs)
            check_response(response)
            logger.info('Measurement submitted successfully to file %s'
                        % run_data[param_names['filename']])
        except Exception:
            logger.exception("Measurement on channel %s failed."
                             % stimulus_channel)


def parse_args():
    parser = argparse.ArgumentParser('Automatically run SIP measurements.')
    parser.add_argument('--paramfile', required=False,
                        help='Parameter file overwriting the defaults in json '
                        'format. For available variable names, see '
                        'PARAM_NAMES in the source code of this script.'
                        'For default values, see DEFAULTS in the source code.')
    parser.add_argument('--channels-file', type=str, required=True,
                        help='JSON file that maps stimulus channel number to '
                        'a list of measurement channel numbers.')
    parser.add_argument('--basename', required=True, type=str,
                        help='Suffix for each file created on the measurement '
                        'device. It will automatically be prefixed with date, '
                        'time and channel.')
    parser.add_argument('--interval', required=True, type=str,
                        help='Interval of the measurements given in HH:MM.')
    parser.add_argument('--ip', required=True, type=str, help='IP address of '
                        'measurement device. Check with ipconfig on device.')
    parser.add_argument('--logfile', type=str, help='File to write log to. If it is not specified,'
                        'logs will be written to an automatically generated file.')
    parser.add_argument('--sip-version', required=False, type=str,
                        choices=['1.0.1', '1.3.1h-1'], default='1.3.1h-1',
                        help='Version number of the SIP software. '
                        'Currently, only version 1.0.1 and 1.3.1h-1 are supported.')
    parser.add_argument('--measure-full-hours', required=False, action='store_true',
                        help='Option to schedule time measurements in a way'
                        ' that they will match the full hour. '
                        'This means that they do not start right away, '
                        'but n * interval before the next full hour. '
                        '(where n is the maximum number of times that interval '
                        'fits into the time until the full hour.) '
                        'Otherwise, measurements start right away.')
    args = parser.parse_args()

    if args.paramfile is None:
        data = {}
    else:
        with open(args.paramfile, 'r') as file:
            data = json.load(file)

    with open(args.channels_file, 'r') as file:
        args.channels = json.load(file)

    if args.logfile is not None:
        logfile = args.logfile
    else:
        now = arrow.utcnow().strftime("%Y%m%dT%H%M%SZ")
        logfile = '%s-%s-autorun.log' % (now, args.basename)
    args.logfile = logfile

    return args, data


def main():
    args, data = parse_args()

    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(filename=args.logfile),
        ])

    default = DEFAULTS.copy()
    default.update(data)
    data = default
    data["filename"] = args.basename
    param_names = get_param_names(args.sip_version)
    logger.info('Parameters are: %s' % data)
    logger.info('Channel mapping is: %s' % args.channels)

    # Retreive authentication data from user
    if args.sip_version == '1.3.1h-1':
        print('Please enter your authentication data for the SIP server.')
        user_name = input('Login name: ')
        password = getpass.getpass()
        request_kwargs = {'auth': (user_name, password)}
    else:
        request_kwargs = {}

    # Start meaurement in given intervals
    interval = get_interval(args.interval)
    if args.measure_full_hours:
        print(args.measure_full_hours)
        next_time = first_measure_time(interval)
        wait_until(next_time)
    else:
        next_time = arrow.utcnow()
    measure(data, param_names, args, request_kwargs)
    while True:
        next_time = next_time + interval
        wait_until(next_time)
        measure(data, param_names, args, request_kwargs)


if __name__ == '__main__':
    main()
