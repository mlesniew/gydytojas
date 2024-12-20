#!/usr/bin/env python3
# -*- coding: utf8 -*-

import argparse
import functools
import base64
import collections
import datetime
import difflib
import getpass
import hashlib
import random
import re
import string
import sys
import time
import uuid
import urllib.parse

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tabulate import tabulate
import requests


Visit = collections.namedtuple("Visit", "date specialty doctor clinic visit_id phone_consultation")


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def parse_datetime(t, maximize=False):
    FORMATS = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%dT%H",
        "%Y-%m-%d %H",
        "%Y.%m.%d %H",
        "%Y-%m-%d",
        "%Y.%m.%d",
    ]
    t = str(t).strip()

    # drop timezone
    t = re.sub(r"[+-][0-9]{2}:?[0-9]{2}$", "", t).strip()

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
            if "%M" not in time_format and maximize:
                ret = ret.replace(minute=59)
            if "%H" not in time_format and maximize:
                ret = ret.replace(hour=23)
            return ret

    raise ValueError


class Time(datetime.time):
    @classmethod
    def parse(cls, spec):
        elements = spec.strip().split(":")
        if len(elements) > 3:
            raise ValueError
        elements = [int(e) for e in elements] + [0, 0]
        return cls(elements[0], elements[1], elements[2])

    def __str__(self):
        return self.strftime("%H:%M:%S")


class Timerange(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end

    @classmethod
    def parse(cls, spec):
        elements = spec.strip().split("-")
        if len(elements) != 2:
            raise ValueError
        return cls(Time.parse(elements[0]), Time.parse(elements[1]))

    def __str__(self):
        return f"{self.start}-{self.end}"

    def covers(self, dt):
        return self.start <= dt.time() <= self.end


def format_datetime(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def parse_timedelta(t):
    p = re.compile(r"((?P<days>\d+?)(d))?\s*((?P<hours>\d+?)(hr|h))?\s*((?P<minutes>\d+?)(m))?$")
    m = p.match(t)
    if not m:
        raise ValueError
    days = m.group("days")
    hours = m.group("hours")
    minutes = m.group("minutes")
    if not (days or hours or minutes):
        raise ValueError
    days = int(days or "0")
    hours = int(hours or "0")
    minutes = int(minutes or "0")

    return datetime.timedelta(days=days, hours=hours, minutes=minutes)


def Soup(response):
    return BeautifulSoup(response.content, "html.parser")


def extract_form_data(form):
    fields = form.findAll("input")
    return {field.get("name"): field.get("value") for field in fields}


class Medicover:
    LOGIN_URL = "https://login-online24.medicover.pl"
    OIDC_REDIRECT = "https://online24.medicover.pl/signin-oidc"

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.session()
        self.session.headers.update(
            {
                "User-Agent": UserAgent().random,
                "Accept": "application/json",
                # "Authorization": None
            }
        )
        self.session.hooks = {"response": lambda r, *args, **kwargs: r.raise_for_status()}
        self.filters = collections.defaultdict(dict)
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None

    def login(self):
        eprint(f"Logging in (username: {self.username})")

        def generate_code_challenge(input):
            sha256 = hashlib.sha256(input.encode("utf-8")).digest()
            return base64.urlsafe_b64encode(sha256).decode("utf-8").rstrip("=")

        state = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
        device_id = str(uuid.uuid4())
        code_verifier = "".join(uuid.uuid4().hex for _ in range(3))
        code_challenge = generate_code_challenge(code_verifier)

        auth_params = (
            f"?client_id=web&redirect_uri={self.OIDC_REDIRECT}&response_type=code"
            f"&scope=openid+offline_access+profile&state={state}&code_challenge={code_challenge}"
            "&code_challenge_method=S256&response_mode=query&ui_locales=pl&app_version=3.2.0.482"
            f"&previous_app_version=3.2.0.482&device_id={device_id}&device_name=Chrome"
        )

        # Step 1: Initialize login
        response = self.session.get(f"{self.LOGIN_URL}/connect/authorize{auth_params}", allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 2: Extract CSRF token
        response = self.session.get(next_url, allow_redirects=False)
        soup = Soup(response)
        csrf_token = soup.find("input", {"name": "__RequestVerificationToken"}).get("value")

        # Step 3: Submit login form
        login_data = {
            "Input.ReturnUrl": f"/connect/authorize/callback{auth_params}",
            "Input.LoginType": "FullLogin",
            "Input.Username": self.username,
            "Input.Password": self.password,
            "Input.Button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        response = self.session.post(next_url, data=login_data, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 4: Fetch authorization code
        response = self.session.get(f"{self.LOGIN_URL}{next_url}", allow_redirects=False)
        next_url = response.headers.get("Location")
        code = urllib.parse.parse_qs(urllib.parse.urlparse(next_url).query)["code"][0]

        # Step 5: Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "redirect_uri": self.OIDC_REDIRECT,
            "code": code,
            "code_verifier": code_verifier,
            "client_id": "web",
        }
        response = self.session.post(f"{self.LOGIN_URL}/connect/token", data=token_data)
        tokens = response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        self.session.headers["Authorization"] = f"Bearer {self.access_token}"
        self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=tokens["expires_in"])

    @property
    def logged_in(self):
        return bool(self.access_token)

    def refresh_token_if_near_expiry(self, margin=20):
        if not self.logged_in:
            return
        if datetime.datetime.now() + datetime.timedelta(seconds=margin) < self.token_expiry:
            return
        eprint("Refreshing token...")
        del self.session.headers["Authorization"]
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": "web",
            "scope": "openid+offline_access+profile",
        }
        response = self.session.post("https://login-online24.medicover.pl/connect/token", data=token_data)
        tokens = response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        self.session.headers["Authorization"] = f"Bearer {self.access_token}"
        self.token_expiry = datetime.datetime.now() + datetime.timedelta(seconds=tokens["expires_in"])

    def sleep(self, seconds, margin=10):
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        # TODO: This is nasty, fix this...
        while datetime.datetime.now() < end_time:
            self.refresh_token_if_near_expiry(margin)
            time.sleep(0.5)

    @functools.cache
    def load_filters(self, region_id=None, specialty_id=None):
        params = {"SlotSearchType": "0"}
        if region_id:
            params["RegionIds"] = region_id
        if specialty_id:
            params["SpecialtyIds"] = specialty_id
        response = self.session.get(
            "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/filters", params=params
        )
        for category, mapping in response.json().items():
            self.filters[category].update({e["value"].strip(): e["id"] for e in mapping})

    @functools.cached_property
    def personal_data(self):
        response = self.session.get("https://api-gateway-online24.medicover.pl/personal-data/api/personal")
        return response.json()

    @property
    def home_region_id(self):
        return self.personal_data["homeClinicId"]

    @staticmethod
    def match_param(mapping, text):
        matches = difflib.get_close_matches(text.lower(), list(mapping), 1, 0.1)
        if not matches:
            raise SystemExit(f'Error translating "{text}" to an id.')
        match = matches[0]
        ret = mapping[match]
        eprint(f'Translated "{text}" to id "{ret}" ("{match}").')
        return ret

    def get_search_params(self, region, specialties, doctors=[], clinics=[]):
        if not region:
            region_id = self.home_region_id
            eprint(f'Using home region id "{region_id}"')
        else:
            self.load_filters()
            region_id = self.match_param(self.filters["regions"], region)

        self.load_filters(region_id)
        specialty_ids = [self.match_param(self.filters["specialties"], specialty) for specialty in specialties]

        for specialty_id in specialty_ids:
            self.load_filters(region_id, specialty_id)

        params = {
            "SlotSearchType": "0",
            "Page": "1",
            "PageSize": "5000",
            "VisitType": "Center",
        }
        if region_id:
            params["RegionIds"] = region_id
        if specialty_id:
            params["SpecialtyIds"] = specialty_ids
        if clinics:
            params["ClinicIds"] = [self.match_param(self.filters["clinics"], clinic) for clinic in clinics]
        if doctors:
            params["DoctorIds"] = [self.match_param(self.filters["doctors"], doctor) for doctor in doctors]

        return params

    def search(self, region, specialties, doctors, clinics, after=None, before=None):
        after = after or datetime.datetime.now()
        before = before or after + datetime.timedelta(days=30)

        after = max(datetime.datetime.now(), after)

        while after < before:
            self.refresh_token_if_near_expiry()
            params = self.get_search_params(region, specialties, doctors, clinics)
            params["StartTime"] = after.date().isoformat()
            response = self.session.get(
                "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/slots", params=params
            )
            data = response.json()

            if not data["items"]:
                # no more visits
                break

            for visit in data["items"]:
                yield Visit(
                    parse_datetime(visit["appointmentDate"]),
                    visit["specialty"]["name"],
                    visit["doctor"]["name"],
                    visit["clinic"]["name"],
                    visit["bookingString"],
                    visit["visitType"] != "Center",
                )

            if next_search_date := data["nextSearchDate"]:
                after = parse_datetime(next_search_date)
            else:
                break

    def book(self, visit):
        self.refresh_token_if_near_expiry()
        data = {"bookingString": visit.visit_id, "metadata": {"appointmentSource": "Direct"}}
        response = self.session.post(
            "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/book-appointment", json=data
        )
        eprint(f"Booked appointment, id = {response.json()['appointmentId']}")


def main():
    parser = argparse.ArgumentParser(description="Check Medicover visit availability")

    parser.add_argument("--region", "-r", help="Region")
    parser.add_argument("--username", "--user", "-u", help="user name used for login")
    parser.add_argument("--password", "--pass", "-p", help="password used for login")

    parser.add_argument(
        "specialty",
        nargs="+",
        help="desired specialty, multiple can be given",
    )

    parser.add_argument(
        "--doctor",
        "--doc",
        "-d",
        action="append",
        help="desired doctor, multiple can be given",
    )

    parser.add_argument("--clinic", "-c", action="append", help="desired clinic, multiple can be given")

    parser.add_argument(
        "--after",
        "-A",
        default="2000-01-01",
        type=parse_datetime,
        metavar="start time",
        help="search period start time.",
    )

    parser.add_argument(
        "--before",
        "-B",
        default="2100-01-01",
        type=lambda t: parse_datetime(t, True),
        metavar="end time",
        help="search period end time",
    )

    parser.add_argument(
        "--margin",
        "-m",
        default="1h",
        type=parse_timedelta,
        metavar="margin",
        help="minimum time from now till the visit",
    )

    parser.add_argument(
        "--autobook",
        "--auto",
        "-a",
        action="store_true",
        help="automatically book the first available visit",
    )

    parser.add_argument(
        "--keep-going",
        "-k",
        action="store_true",
        help="retry until a visit is found or booked",
    )

    parser.add_argument(
        "--diagnostic-procedure",
        action="store_true",
        help="search for diagnostic procedures instead of consultations",
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=-60,
        help="interval between retries in seconds, "
        "use negative values to sleep random time up to "
        "the given amount of seconds",
    )

    parser.add_argument(
        "--phone",
        "-P",
        action="store_true",
        help="Also search for phone consultations (disabled by default)",
    )

    parser.add_argument("--time", type=Timerange.parse, help="acceptable visit time range")

    args = parser.parse_args()

    username = args.username or input("user: ")
    password = args.password or getpass.getpass("pass: ")

    medicover = Medicover(username, password)

    eprint("Searching for appointments...")
    attempt = 0
    while True:
        attempt += 1

        after = max(args.after, datetime.datetime.now() + args.margin)
        before = args.before

        if after >= before:
            raise SystemExit("It's already too late")

        if not medicover.logged_in:
            medicover.login()

        visits = medicover.search(args.region, args.specialty, args.doctor, args.clinic, after, before)

        if not args.phone:
            visits = (v for v in visits if not v.phone_consultation)

        # we might have found visits outside the interesting time range
        visits = (v for v in visits if after <= v.date <= before)

        # filter out the visits, which don't cover the desired time
        if args.time:
            visits = (v for v in visits if args.time.covers(v.date))

        visits = list(sorted(visits))

        if visits:
            eprint(f"Found {len(visits)} visits.")
            print(tabulate([v[:4] for v in visits], headers=Visit._fields[:4]))

            if args.autobook:
                visit = visits[0]
                medicover.book(visit)
                break
        else:
            if not args.keep_going:
                raise SystemExit("No visits found.")

            # nothing found, but we'll retry
            if args.interval:
                if args.interval > 0:
                    sleep_time = args.interval
                else:
                    sleep_time = -1 * args.interval * random.random()
                eprint(f"No visits found on {attempt} attempt, waiting {sleep_time:.1f} seconds...")
                medicover.sleep(sleep_time)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Abort.")
