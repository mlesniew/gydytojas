# gydytojas

Medicover visit availability checking and automatic booking.

## Usage

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
