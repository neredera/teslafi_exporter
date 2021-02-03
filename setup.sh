#!/bin/bash

# go to current directory
cd "${0%/*}"

# install needed packages
sudo apt-get install git python3-venv python3-pip

# activate a virtual environment
python3 -m venv .

# install python modules
python3 -m pip install prometheus_client requests

# user for service
useradd -Mr teslafi_exporter
usermod -L teslafi_exporter
# usermod -aG root teslafi_exporter
# usermod -aG sudo teslafi_exporter

chmod +x exporter.py

# sudo systemctl daemon-reload

sudo systemctl enable $(pwd)/teslafi_exporter.service

sudo systemctl start teslafi_exporter.service

python3 exporter.py --help

sudo systemctl status teslafi_exporter.service
