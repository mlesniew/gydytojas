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


Visit = collections.namedtuple('Visit', 'date specialization doctor clinic visit_id')


session = requests.session()
session.headers['accept'] = 'application/json'
session.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/69.0.3497.81 Chrome/69.0.3497.81 Safari/537.36'
session.hooks = {
        'response': lambda r, *args, **kwargs: r.raise_for_status()
        }


def parse_datetime(t):
    FORMATS = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%Y.%m.%d %H:%M:%S',
        '%Y.%m.%d %H:%M',
        '%Y-%m-%d',
    ]
    t = str(t).strip()

    # drop timezone
    t = re.sub(r'[+-][0-9]{2}:?[0-9]{2}$', '', t).strip()

    for time_format in FORMATS:
        try:
            return datetime.datetime.strptime(t, time_format)
        except ValueError:
            continue

    raise ValueError


def format_datetime(t):
    return t.strftime('%Y-%m-%dT%H:%M:%S')


def Soup(response):
    return BeautifulSoup(response.content, 'lxml')


def extract_form_data(form):
    fields = form.findAll('input')
    return {field.get('name'): field.get('value') for field in fields}


def unescape(text):
    return HTMLParser().unescape(text)


def login(username, password):
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
    print('Logged in.')


def setup_params(region, specialization, clinic=None, doctor=None):
    def find_id(table, name):
        mapping = {e['text'].lower(): e['id'] for e in table if e.get('id') >= 0}
        matches = difflib.get_close_matches(name.lower(), list(mapping), 1, 0.1)

        if not matches:
            print('Error resolving %s to an id.  Available values are:' % name)
            for name in sorted(mapping):
                print(' * %s' % name)
            raise SystemExit("Can't resolve %s to an ID" % name)

        ret = mapping[matches[0]]
        print('Assuming "%s" is "%s" with id = %i' % (name, matches[0].title(), ret))
        return ret

    def update_params(element_name, json_name, expected_value):
        if expected_value is None:
            return
        resp = session.get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/FormModel',
                           params=params)
        data = resp.json()

        if data[json_name]:
            params[element_name] = find_id(data[json_name], expected_value)
        else:
            print("Can't select a %s for this search, skipping constraint." % element_name)

    # Open the main visit search page to pretend we're a browser
    session.get('https://mol.medicover.pl/MyVisits')

    # Setup some params initially
    params = {
        'regionId': -1,
        'bookingTypeId': 2,
        'specializationId': -2
    }

    update_params('regionId', 'availableRegions', region)
    update_params('specializationId', 'availableSpecializations', specialization)
    update_params('clinicId', 'availableClinics', clinic)
    update_params('doctorId', 'availableDoctors', doctor)

    return params


def search(start_time, end_time, params):
    payload = {
        "regionId": -1,
        "bookingTypeId": 2,
        "specializationId": None,
        "clinicId": -1,
        "languageId": -1,
        "doctorId": None,
        "periodOfTheDay": 0,
        "isSetBecauseOfPcc": False,
        "isSetBecausePromoteSpecialization": False
    }
    payload.update(params)

    start_time = max(datetime.datetime.now(), start_time).replace(hour=0, minute=0, second=0, microsecond=0)
    since_time = start_time

    DELTA = datetime.timedelta(days=1)

    # Opening these addresses seems retarded, but it is needed, i guess it sets some cookies
    session.get('https://mol.medicover.pl/MyVisits')

    print('Searching for visits...')
    while True:
        print('  ...%s' % since_time)
        payload['searchSince'] = format_datetime(start_time)
        payload['searchForNextSince'] = format_datetime(since_time) if since_time else None
        params = {
            "language": "pl-PL"
        }
        resp = session.post('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook',
                            params=params,
                            json=payload)
        data = resp.json()

        collected_count = 0
        for visit in data['items']:
            collected_count += 1
            yield Visit(
                parse_datetime(visit['appointmentDate']),
                visit['specializationName'],
                visit['doctorName'],
                visit['clinicName'],
                visit['id'])

        first_possible = parse_datetime(data['firstPossibleAppointmentDate'])
        last_possible = parse_datetime(data['lastPossibleAppointmentDate'])

        if last_possible.year < 2000:
            print('No visits available.')
            break

        if (since_time < first_possible):
            since_time = first_possible
        else:
            since_time += DELTA

        if since_time > last_possible:
            print('Passed last possible appointment date %s.' % last_possible)
            break

        if since_time > end_time:
            print('Passed desired max time: %s' % end_time)
            break

        if collected_count == 0:
            print('No more visits (?)')
            break


def autobook(visit):
    print('Autobooking first visit...')
    params = {'id': visit.visit_id}
    resp = session.get('https://mol.medicover.pl/MyVisits/Process/Process', params=params)
    resp = session.get('https://mol.medicover.pl/MyVisits/Process/Confirm', params=params)

    soup = Soup(resp)
    form = soup.find('form', action="/MyVisits/Process/Confirm")
    resp = session.post('https://mol.medicover.pl/MyVisits/Process/Confirm', data=extract_form_data(form))


def main():
    parser = argparse.ArgumentParser(description='Check Medicover visit availability')

    parser.add_argument('--region', '-r',
                        default='Kraków',
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
                        help='search period start time.')

    parser.add_argument('--end', '--until', '--till', '--to', '-t',
                        default='2100-01-01',
                        type=parse_datetime,
                        help='search period end time')

    parser.add_argument('--autobook', '--auto', '-a',
                        action='store_true',
                        help='automatically book the first available visit')

    parser.add_argument('--keep-going', '-k',
                        action='store_true',
                        help='retry until a visit is found or booked')

    parser.add_argument('--interval', '-i',
                        type=int,
                        default=5,
                        help='interval between retries in seconds, '
                             'use negative values to sleep random time up to '
                             'the given amount of seconds')

    args = parser.parse_args()

    username = args.username or raw_input('user: ')
    password = args.password or getpass.getpass('pass: ')

    now = datetime.datetime.now()
    start = max(args.start, now)
    end = args.end

    if now > end:
        raise SystemExit("It's already too late")

    print('Searching for visits between %s and %s.' % (start, end))

    login(username, password)

    doctors = args.doctor or [None]
    clinics = args.clinic or [None]

    visits = set()
    params = []
    for specialization in args.specialization:
        for clinic in clinics:
            for doctor in doctors:
                print('Processing %s / %s / %s / %s' % (args.region,
                                                        specialization,
                                                        clinic or '<any clinic>',
                                                        doctor or '<any doctor>'))
                params.append(setup_params(args.region, specialization, clinic, doctor))

    while True:
        visits = itertools.chain.from_iterable(search(start, end, p) for p in params)

        # we might have found visits outside the interesting time range
        visits = [v for v in visits if start <= v.date <= end]

        unique_visits = sorted(set(v[:4] for v in visits))

        if not unique_visits:
            print('No visits found.')
        else:
            print('Found %i visits.' % len(unique_visits))
            print(tabulate(
                unique_visits,
                headers=Visit._fields[:4]))

        if not visits and args.keep_going:
            # nothing found, but we'll retry
            if args.interval:
                if args.interval > 0:
                    sleep_time = args.interval
                else:
                    sleep_time = -1 * args.interval * random.random()
                print('Sleeping %.1f seconds' % sleep_time)
                time.sleep(sleep_time)
            print('Retrying...')
            continue

        if not args.autobook:
            return

        if not visits:
            raise SystemExit('No visits -- not booking')

        visit = sorted(visits)[0]
        autobook(visit)
        break


if __name__ == '__main__':
    main()
