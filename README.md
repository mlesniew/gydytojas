# gydytojas

Medicover visit availability checking and automatic booking.

## Usage

```
usage: gydytojas.py [-h] [--region REGION] [--username USERNAME]
                    [--password PASSWORD] [--doctor DOCTOR] [--clinic CLINIC]
                    [--start START] [--end END] [--autobook] [--keep-going]
                    [--interval INTERVAL]
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
  --start START, --from START, -f START
                        search period start time.
  --end END, --until END, --till END, --to END, -t END
                        search period end time
  --autobook, --auto, -a
                        automatically book the first available visit
  --keep-going, -k      retry until a visit is found or booked
  --interval INTERVAL, -i INTERVAL
                        interval between retries in seconds, use negative
                        values to sleep random time up to the given amount of
                        seconds
```
