#!/usr/bin/env python3
# -*- coding: utf8 -*-

from __future__ import unicode_literals
from __future__ import print_function

try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser

import argparse
import collections
import datetime
import difflib
import getpass
import itertools
import json
import random
import re
import time

from bs4 import BeautifulSoup
from tabulate import tabulate
import requests
from halo import Halo


Visit = collections.namedtuple('Visit', 'date specialization doctor clinic visit_id')


session = requests.session()
session.headers['accept'] = 'application/json'
session.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/69.0.3497.81 Chrome/69.0.3497.81 Safari/537.36'
session.hooks = {
        'response': lambda r, *args, **kwargs: r.raise_for_status()
        }


class Spinner(Halo):
    def __exit__(self, ex_type, ex_value, ex_traceback):
        if ex_value:
            self.fail(str(ex_value) or None)
        elif self.spinner_id:
            self.succeed()
        else:
            self.stop()


def parse_datetime(t, maximize=False):
    FORMATS = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y.%m.%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M',
        '%Y.%m.%d %H:%M',
        '%Y-%m-%dT%H',
        '%Y-%m-%d %H',
        '%Y.%m.%d %H',
        '%Y-%m-%d',
        '%Y.%m.%d',
    ]
    t = str(t).strip()

    # drop timezone
    t = re.sub(r'[+-][0-9]{2}:?[0-9]{2}$', '', t).strip()

    for time_format in FORMATS:
        try:
            ret = datetime.datetime.strptime(t, time_format)
        except ValueError:
            continue
        else:
            if maximize:
                ret = ret.replace(second=59, microsecond=999999)
            else:
                ret = ret.replace(second=0, microsecond=0)
            if '%M' not in time_format and maximize:
                ret = ret.replace(minute=59)
            if '%H' not in time_format and maximize:
                ret = ret.replace(hour=23)
            return ret

    raise ValueError


def format_datetime(t):
    return t.strftime('%Y-%m-%dT%H:%M:%S')


def parse_timedelta(t):
    p = re.compile(r'((?P<days>\d+?)(d))?\s*((?P<hours>\d+?)(hr|h))?\s*((?P<minutes>\d+?)(m))?$')
    m = p.match(t)
    if not m:
        raise ValueError
    days = m.group('days')
    hours = m.group('hours')
    minutes = m.group('minutes')
    if not (days or hours or minutes):
        raise ValueError
    days = int(days or '0')
    hours = int(hours or '0')
    minutes = int(minutes or '0')

    return datetime.timedelta(days=days, hours=hours, minutes=minutes)


def Soup(response):
    return BeautifulSoup(response.content, 'lxml')


def extract_form_data(form):
    fields = form.findAll('input')
    return {field.get('name'): field.get('value') for field in fields}


def unescape(text):
    return HTMLParser().unescape(text)


def login(username, password):
    with Spinner('Login'):
        resp = session.get('https://mol.medicover.pl/Users/Account/LogOn')

        # remember URL to post to
        post_url = resp.url

        # parse the html response
        soup = Soup(resp)

        # Extract some retarded token, which needs to be submitted along with the login
        # information.  The token is a JSON object in a special html element somewhere
        # deep in the page.  The JSON data has some chars escaped to not break the html.
        mj_element = soup.find(id='modelJson')
        mj = json.loads(unescape(mj_element.text))
        af = mj['antiForgery']

        # This is where the magic happens
        resp = session.post(
                post_url,
                data={
                    'username': username,
                    'password': password,
                    af['name']: af['value'],
                    }
                )

        # After posting the login information and the retarded token, we should get
        # redirected to some other page with a hidden form.  Apparently in the browser
        # some JS script simply takes that form and posts it again.  Let's do the
        # same.
        soup = Soup(resp)
        form = soup.form
        if not (('/connect/authorize' in resp.url) and form):
            raise SystemExit('Login failed')
        resp = session.post(form['action'], data=extract_form_data(form))

        # If all went well, we should be logged in now.  Try to open the main page...
        resp = session.get('https://mol.medicover.pl/')

        if resp.url != 'https://mol.medicover.pl/':
            # We got redirected, probably the login failed and it sent us back to the
            # login page.
            raise SystemExit('Login failed.')

        # we're in, lol


def setup_params(region, service_type, specialization, clinics=None, doctor=None):
    with Spinner('Setup search parameters (%s / %s / %s / %s / %s)' % (
        region, service_type, specialization, clinics, doctor)):

        params = {}

        # Open the main visit search page to pretend we're a browser
        session.get('https://mol.medicover.pl/MyVisits')

        resp = session.get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/GetInitialFiltersData')
        data = resp.json()

        def match_param(data, key, text):
            mapping = {e['text'].lower(): e['id'] for e in data.get(key, [])}
            matches = difflib.get_close_matches(text.lower(), list(mapping), 1, 0.1)
            if not matches:
                raise SystemExit('Error translating %s "%s" to an id.' % (key, text))
            return mapping[matches[0]]

        # if no region was specified, use the default provided by the API
        if region:
            params['regionIds'] = [match_param(data, 'regions', region)]
        else:
            params['regionIds'] = [data['homeLocationId']]

        params['serviceTypeId'] = str(match_param(data, 'serviceTypes', service_type))

        # serviceId / specialization
        data = session.get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/GetFiltersData',
                           params=params).json()
        params['serviceIds'] = [str(match_param(data, 'services', specialization))]

        # clinics
        if clinics:
            data = session.get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/GetFiltersData',
                               params=params).json()
            params['clinicIds'] = [match_param(data, 'clinics', clinic) for clinic in clinics]

        if doctor:
            data = session.get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/GetFiltersData',
                               params=params).json()
            # for some reason this must be a string, not an int in the posted json
            params['doctorIds'] = [str(match_param(data, 'doctors', doctor))]

        return params


def search(start_time, end_time, params):
    payload = {
            "regionIds": [],
            "serviceTypeId": "1",
            "serviceIds": [],
            "clinicIds": [],
            "doctorLanguagesIds":[],
            "doctorIds":[],
            "searchSince":None
            }
    payload.update(params)

    since_time = max(datetime.datetime.now(), start_time)
    ONE_DAY = datetime.timedelta(days=1)

    while True:
        payload['searchSince'] = format_datetime(since_time)
        max_appointment_date = None
        params = {
            "language": "pl-PL"
        }
        resp = session.post('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook',
                            params=params,
                            json=payload)
        data = resp.json()

        if not data['items']:
            # no more visits
            break

        for visit in data['items']:
            appointment_date = parse_datetime(visit['appointmentDate'])
            max_appointment_date = max(max_appointment_date or appointment_date,
                                       appointment_date)
            yield Visit(
                appointment_date,
                visit['specializationName'],
                visit['doctorName'],
                visit['clinicName'],
                visit['id'])

        since_time = max_appointment_date.replace(hour=0, minute=0, second=0, microsecond=0) + ONE_DAY

        if since_time > end_time:
            # passed desired max time
            break


def autobook(visit):
    with Spinner('Autobooking first visit'):
        params = {'id': visit.visit_id}
        resp = session.get('https://mol.medicover.pl/MyVisits/Process/Process', params=params)
        resp = session.get('https://mol.medicover.pl/MyVisits/Process/Confirm', params=params)

        soup = Soup(resp)
        form = soup.find('form', action="/MyVisits/Process/Confirm")
        resp = session.post('https://mol.medicover.pl/MyVisits/Process/Confirm', data=extract_form_data(form))


def main():
    parser = argparse.ArgumentParser(description='Check Medicover visit availability')

    parser.add_argument('--region', '-r',
                        help='Region')

    parser.add_argument('--username', '--user', '-u',
                        help='user name used for login')

    parser.add_argument('--password', '--pass', '-p',
                        help='password used for login')

    parser.add_argument('specialization',
                        nargs='+',
                        help='desired specialization, multiple can be given')

    parser.add_argument('--doctor', '--doc', '-d',
                        action='append',
                        help='desired doctor, multiple can be given')

    parser.add_argument('--clinic', '-c',
                        action='append',
                        help='desired clinic, multiple can be given')

    parser.add_argument('--start', '--from', '-f',
                        default='2000-01-01',
                        type=parse_datetime,
                        metavar='start time',
                        help='search period start time.')

    parser.add_argument('--end', '--until', '--till', '--to', '-t',
                        default='2100-01-01',
                        type=lambda t: parse_datetime(t, True),
                        metavar='end time',
                        help='search period end time')

    parser.add_argument('--margin', '-m',
                        default='1h',
                        type=parse_timedelta,
                        metavar='margin',
                        help='minimum time from now till the visit')

    parser.add_argument('--autobook', '--auto', '-a',
                        action='store_true',
                        help='automatically book the first available visit')

    parser.add_argument('--keep-going', '-k',
                        action='store_true',
                        help='retry until a visit is found or booked')

    parser.add_argument('--diagnostic-procedure',
                        action='store_true',
                        help='search for diagnostic procedures instead of consultations')

    parser.add_argument('--interval', '-i',
                        type=int,
                        default=5,
                        help='interval between retries in seconds, '
                             'use negative values to sleep random time up to '
                             'the given amount of seconds')

    args = parser.parse_args()

    username = args.username or raw_input('user: ')
    password = args.password or getpass.getpass('pass: ')

    login(username, password)

    visit_type = 'Badanie diagnostyczne' if args.diagnostic_procedure else 'Konsultacja'
    doctors = args.doctor or [None]
    clinics = args.clinic

    visits = set()
    params = []
    for specialization in args.specialization:
        for doctor in doctors:
            params.append(setup_params(args.region, visit_type, specialization, clinics, doctor))

    with Spinner('Searching for visits...') as spinner:
        attempt = 0
        while True:
            attempt += 1

            if args.keep_going:
                spinner.text = 'Searching for visits (attempt %i)' % attempt

            start = max(args.start, datetime.datetime.now() + args.margin)
            end = args.end

            if start >= end:
                raise SystemExit("It's already too late")

            visits = itertools.chain.from_iterable(search(start, end, p) for p in params)

            # we might have found visits outside the interesting time range
            visits = [v for v in visits if start <= v.date <= end]

            unique_visits = sorted(set(v[:4] for v in visits))

            if not unique_visits and args.keep_going:
                # nothing found, but we'll retry
                if args.interval:
                    if args.interval > 0:
                        sleep_time = args.interval
                    else:
                        sleep_time = -1 * args.interval * random.random()
                    spinner.text = 'No visits found on %i attempt, waiting %.1f seconds' % (attempt, sleep_time)
                    time.sleep(sleep_time)
                continue

            if not unique_visits:
                spinner.fail('No visits found')
            else:
                spinner.succeed('Found %i visits' % len(unique_visits))
                print(tabulate(
                    unique_visits,
                    headers=Visit._fields[:4]))

            if not args.autobook:
                return

            if not visits:
                raise SystemExit('No visits -- not booking')

            visit = sorted(visits)[0]
            autobook(visit)
            break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('Abort.')
