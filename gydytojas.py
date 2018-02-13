#!/usr/bin/env python
# -*- coding: utf8 -*-

from __future__ import unicode_literals

import datetime
import json
from HTMLParser import HTMLParser
import difflib

from bs4 import BeautifulSoup
from tabulate import tabulate
import dateparser
import requests

# --- DO YOUR CHANGES HERE ---

# Login information
USERNAME = '1100101'
PASSWORD = 'secret'

# Date range of visits to check
FROM = dateparser.parse('2018-01-22 16:20')
UNTIL = dateparser.parse('2018-01-26 19:00')

# Names of clinics, doctors etc don't have to be spelled exactly right, the
# script is pretty good at guessing what you meant.

# Your city
REGION = 'Krakow'

# list of specializations, must not be empty
SPECIALIZATION = ['Medicover express -- przeziebinie', 'Medycyna rodzinna dorośli', 'Internista']

# list or empty for any
CLINIC = ['Bora Komorowskiego', 'Podgorska']
DOCTOR = []

# Change to true to automatically book the first available visit
AUTOBOOK = False

# ----------------------------


class Visit(object):

    def __init__(self, date, spec, doctor, clinic, visit_id):
        self.date = date
        self.spec = spec
        self.doctor = doctor
        self.clinic = clinic
        self.visit_id = visit_id

    @property
    def elements(self):
        return self.date, self.spec, self.doctor, self.clinic

    def __hash__(self):
        return hash(self.elements)

    def __eq__(self, other):
        return self.elements == other.elements

    def __lt__(self, other):
        return self.elements < other.elements

    def __str__(self):
        return '%s -- %s -- %s -- %s' % (self.date, self.spec, self.doctor, self.clinic)


session = requests.session()


def get(*args, **kwargs):
    ret = session.get(*args, **kwargs)
    ret.raise_for_status()
    return ret


def post(*args, **kwargs):
    ret = session.post(*args, **kwargs)
    ret.raise_for_status()
    return ret


def Soup(response):
    return BeautifulSoup(response.content, 'lxml')


def extract_form_data(form):
    fields = form.findAll('input')
    return {field.get('name'): field.get('value') for field in fields}


def unescape(text):
    return HTMLParser().unescape(text)


def login(username, password):
    resp = get('https://mol.medicover.pl/Users/Account/LogOn')

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
    if not form:
        raise SystemExit('Login failed')
    resp = post(form['action'], data=extract_form_data(form))

    # If all went well, we should be logged in now.  Try to open the main page...
    resp = get('https://mol.medicover.pl/')
    with open('3.html', 'w') as f:
        f.write(resp.text.encode('utf-8'))

    if resp.url != 'https://mol.medicover.pl/':
        # We got redirected, probably the login failed and it sent us back to the
        # login page.
        raise SystemExit('Login failed.')

    # we're in, lol
    print 'Logged in.'


def setup_params(region, specialization, clinic=None, doctor=None):
    def find_id(table, name):
        mapping = {e['text'].lower(): e['id'] for e in table if e.get('id') >= 0}
        matches = difflib.get_close_matches(name.lower(), list(mapping), 1, 0.1)

        if not matches:
            print 'Error resolving %s to an id.  Available values are:' % name
            for name in sorted(mapping):
                print ' * %s' % name
            raise SystemExit("Can't resolve %s to an ID" % name)

        ret = mapping[matches[0]]
        print 'Assuming "%s" is "%s" with id = %i' % (name, matches[0].title(), ret)
        return ret

    def update_params(element_name, json_name, expected_value):
        if expected_value is None:
            return
        headers = {'accept': 'application/json'}
        resp = get('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook/FormModel',
                   params=params, headers=headers)
        data = resp.json()

        if data[json_name]:
            params[element_name] = find_id(data[json_name], expected_value)
        else:
            print "Can't select a %s for this search, skipping constraint." % element_name

    # Open the main visit search page to pretend we're a browser
    get('https://mol.medicover.pl/MyVisits')

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


def search(params):
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

    def ts(t):
        return t.strftime('%Y-%m-%dT%H:%M:%S')

    def pt(t):
        # timezones are for loosers
        if '+' in t:
            t = t.split('+')[0]
        try:
            return dateparser.parse(t)
        except OverflowError:
            return dateparser.parse('2100-01-01')

    start_time = max(datetime.datetime.now(), FROM).replace(hour=0, minute=0, second=0, microsecond=0)
    since_time = start_time

    DELTA = datetime.timedelta(days=1)

    # Opening these addresses seems retarded, but it is needed, i guess it sets some cookies
    get('https://mol.medicover.pl/MyVisits')
    # wtf
    get('https://mol.medicover.pl/MyVisits?bookingTypeId=2&mex=True&pfm=1')

    print 'Searching for visits...'
    while True:
        print '  ...%s' % since_time
        payload['searchSince'] = ts(start_time)
        payload['searchForNextSince'] = ts(since_time) if since_time else None
        params = {
            "language": "pl-PL"
        }
        headers = {'content-type': 'application/json', 'accept': 'application/json'}
        resp = post('https://mol.medicover.pl/api/MyVisits/SearchFreeSlotsToBook',
                    params=params,
                    data=json.dumps(payload),
                    headers=headers)
        data = resp.json()

        collected_count = 0
        for visit in data['items']:
            collected_count += 1
            yield Visit(
                dateparser.parse(visit['appointmentDate']),
                visit['specializationName'],
                visit['doctorName'],
                visit['clinicName'],
                visit['id'])

        first_possible = pt(data['firstPossibleAppointmentDate'])
        last_possible = pt(data['lastPossibleAppointmentDate'])

        if (since_time < first_possible):
            since_time = first_possible
        else:
            since_time += DELTA

        if since_time > last_possible:
            print 'Passed last possible appointment date %s.' % last_possible
            break

        if since_time > UNTIL:
            print 'Passed desired max time: %s' % UNTIL
            break

        if collected_count == 0:
            print 'No more visits (?)'
            break


def autobook(visit):
    print 'Autobooking %s' % visit
    params = {'id': visit.visit_id}
    resp = get('https://mol.medicover.pl/MyVisits/Process/Process', params=params)
    resp = get('https://mol.medicover.pl/MyVisits/Process/Confirm', params=params)

    soup = Soup(resp)
    form = soup.find('form', action="/MyVisits/Process/Confirm")
    resp = post('https://mol.medicover.pl/MyVisits/Process/Confirm', data=extract_form_data(form))


def main():
    login(USERNAME, PASSWORD)

    if datetime.datetime.now() > UNTIL:
        raise SystemExit("It's already too late")

    doctors = DOCTOR or [None]
    clinics = CLINIC or [None]

    visits = set()
    for specialization in SPECIALIZATION:
        for clinic in clinics:
            for doctor in doctors:
                print 'Processing %s / %s / %s / %s' % (REGION, specialization, clinic or '<any clinic>', doctor or '<any doctor>')
                params = setup_params(REGION, specialization, clinic, doctor)
                visits |= set(search(params))

    # we might have found visits outside the interresting time range
    visits = sorted(set(v for v in visits if FROM <= v.date <= UNTIL))

    if not visits:
        print 'No visits found'
        return

    print 'Got %i visits:' % len(visits)
    print tabulate(
        ((v.date, v.clinic, v.spec, v.doctor) for v in visits),
        headers='date clinic specialization doctor'.split())

    if not AUTOBOOK:
        return

    visit = visits[0]
    autobook(visit)


if __name__ == '__main__':
    main()
