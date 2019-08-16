import requests
import arrow
import logging
import time
import argparse
import json


logger = logging.getLogger('autorun-SIP')
logger.setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


DEFAULTS = {
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
PARAM_NAMES = {
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

PORTS = {
    "1": 9344,
    "2": 9345,
    "3": 9346,
    "4": 9347,
}


SUBMIT_BUTTON = '<button name="submit" type="submit" value="1"><b>Submit</b>'
CANCEL_BUTTON = '<button name="submit" type="submit" value="0"><b>Cancel</b>'


def next_measure_time(every_hours=2):
    now = arrow.utcnow()
    hour = now.floor('hour')
    return hour.shift(hours=every_hours)


def wait_until(target_time):
    now = arrow.utcnow()
    diff = (target_time - now).total_seconds()
    logger.info('Waiting until %s for next measurement' % target_time.isoformat())
    time.sleep(diff)


def prepare_data(basename, stimulus_channel, response_channels, **params):
    vals = params.copy()
    vals['filename'] = '%s-ch%s-%s' % (
        arrow.utcnow().strftime("%Y%m%dT%H%MZ"),
        stimulus_channel,
        basename)
    vals['stimulus_channel'] = stimulus_channel
    vals['response_channel'] = ','.join(str(i) for i in response_channels)
    return {instrument_name: vals[name]
            for name, instrument_name in PARAM_NAMES.items()}


def check_device_ready(ip, channels):
    for channel in channels:
        url = 'http://%s:%s' % (ip, PORTS[channel])
        try:
            r = requests.get(url)
        except Exception:
            logger.exception('Could not connect to device. Is the IP address correct? '
                             '(It changes at device reboot!)')
            return False
        if not r.ok:
            logger.exception('Got error code from device.')
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


def measure(data, args):
    logger.info('Starting new measurement.')

    if not check_device_ready(args.ip, args.channels):
        logger.info('Waiting 15 minutes...')
        time.sleep(60 * 15)
        if not check_device_ready(args.ip, args.channels):
            logger.error('Skipping this measurement.')
            return

    for stimulus_channel, response_channels in args.channels.items():
        url = 'http://%s:%s' % (args.ip, PORTS[stimulus_channel])
        logger.info('Measuring stimulus channel %s at response channels %s.'
                    % (stimulus_channel, response_channels))
        try:
            run_data = prepare_data(
                args.basename, stimulus_channel, response_channels, **data)
            response = requests.post(url, data=run_data)
            check_response(response)
            logger.info('Measurement submitted successfully to file %s'
                        % run_data[PARAM_NAMES['filename']])
        except Exception:
            logger.exception("Measurement on channel %s failed."
                             % stimulus_channel)


def parse_args():
    parser = argparse.ArgumentParser('Automatically run SIP measurements.')
    parser.add_argument('--paramfile', required=False,
                        help='Parameter file overwriting the defaults in json '
                        'format. For available variable names, see '
                        'PARAM_NAMES in the source code of this script.')
    parser.add_argument('--channels-file', type=str, required=True,
                        help='JSON file that maps stimulus channel number to '
                        'a list of measurement channel numbers.')
    parser.add_argument('--basename', required=True, type=str,
                        help='Suffix for each file created on the measurement '
                        'device. It will automatically be prefixed with date, '
                        'time and channel.')
    parser.add_argument('--interval-hours', required=True, type=int,
                        help='Run measurements once every `interval-hours`. The '
                        'first measurement will be run right away, after that '
                        'always at the full hour.')
    parser.add_argument('--ip', required=True, type=str, help='IP address of '
                        'measurement device. Check with ipconfig on device.')
    parser.add_argument('--logfile', type=str)
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
    logger.info('Parameters are: %s' % data)
    logger.info('Channel mapping is: %s' % args.channels)

    measure(data, args)
    while True:
        next_time = next_measure_time(args.interval_hours)
        wait_until(next_time)
        measure(data, args)


if __name__ == '__main__':
    main()
