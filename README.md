# teslafis_exporter

This is a [Prometheus exporter](https://prometheus.io/docs/instrumenting/exporters/) for [TeslaFi](https://about.teslafi.com/).

It allows to import the current status of your Tesla into Prometheus.

## Usage

Clone the respoitory und install with:
```bash
git clone https://github.com/neredera/teslafi_exporter.git
cd teslafi_exporter
.\setup.sh
```

Get your TeslaFi API token at [TeslaFi](https://teslafi.com/api.php). No commands are used by this tool, you can disable all when generating the API token.

Enter the API token in `teslafi_exporter.service`:
```bash
nano teslafi_exporter.service

sudo systemctl daemon-reload
sudo systemctl restart teslafi_exporter.service
sudo systemctl status teslafi_exporter.service
```

Command line parameters:
```bash
> python3 exporter.py --help

usage: exporter.py [-h] [--port PORT] [--teslafi_api_token TESLAFI_API_TOKEN]

optional arguments:
  -h, --help            show this help message and exit
  --port PORT           The port where to expose the exporter (default:9998)
  --teslafi_api_token TESLAFI_API_TOKEN
                        TeslaFi API Token from https://teslafi.com/api.php
                        
```

## Prometheus metrics

Example how to add the exporter to the prometheus configuration (`prometheus.yml`):
```yml
  - job_name: teslafi
    scrape_interval: 1m  # Has to be longer than 20s or TeslaFi will block you. By default TeslaFi hat every 60s new data.
    static_configs:
    - targets: ['teslafi-exporter-host.local:9998']
```

For a sampe dashboard see: TODO


