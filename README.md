# gydytojas

Gydytojas is a command line tool for searching for available Medicover visits.  It also supports periodic retries if
no visits are found and automatic booking.


## Usage examples

Assuming we'd like to find available internist visits in Kraków:
```
gydytojas.py --region 'Kraków' --username 888888 --password secret 'Internista'
```

In some cases it can be useful to specify multiple specializations, e.g.:
```
gydytojas.py --region 'Kraków' --username 888888 --password secret 'Internista' 'Medycyna Rodzinna -- dorośli'
```

Searching for visits might give too many results, so we can additionally narrow down the search to a date range:
```
gydytojas.py --region 'Kraków' --username 888888 --password secret --start 2019-01-10 --end 2019-01-12 'Internista'
```

The time boundaries are inclusive -- in the example above the script will try to find visits from 2019-01-10 00:00 to
2019-01-12 23:59.  The `--start` and `--end` switches accept dates and times in ISO format (e.g. `2019-01-10`,
`2019-01-10T10:00:00`, `2019-01-10 10:00:00` and `2019-01-10 10:00` are all fine).  Of course, only one time boundary
can be specified (`--start` xor `--end`).

If there's to many search constraints, a visit may not be available.  In these cases it's worth using the
`--keep-going` switch to make the script retry until a visit is found.  Additionally, the first available visit can be
booked automatically by using `--autobook`:
```
gydytojas.py --username 888888 --password secret --end 2019-01-12 --keep-going --autobook 'Internista'
```


## Full help

```
usage: gydytojas.py [-h] [--region REGION] [--username USERNAME]
                    [--password PASSWORD] [--doctor DOCTOR] [--clinic CLINIC]
                    [--start start time] [--end end time] [--margin margin]
                    [--autobook] [--keep-going] [--interval INTERVAL]
                    specialization [specialization ...]

Check Medicover visit availability

positional arguments:
  specialization        desired specialization, multiple can be given

optional arguments:
  -h, --help            show this help message and exit
  --region REGION, -r REGION
                        Region
  --username USERNAME, --user USERNAME, -u USERNAME
                        user name used for login
  --password PASSWORD, --pass PASSWORD, -p PASSWORD
                        password used for login
  --doctor DOCTOR, --doc DOCTOR, -d DOCTOR
                        desired doctor, multiple can be given
  --clinic CLINIC, -c CLINIC
                        desired clinic, multiple can be given
  --start start time, --from start time, -f start time
                        search period start time.
  --end end time, --until end time, --till end time, --to end time, -t end time
                        search period end time
  --margin margin, -m margin
                        minimum time from now till the visit
  --autobook, --auto, -a
                        automatically book the first available visit
  --keep-going, -k      retry until a visit is found or booked
  --interval INTERVAL, -i INTERVAL
                        interval between retries in seconds, use negative
                        values to sleep random time up to the given amount of
                        seconds
```

## Known bugs

* The script does not detect if autobooking was successful
* When `-k` is used, the session can eventually time out causing an unhandled exception
