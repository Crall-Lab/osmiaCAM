#!/bin/bash

# have job exit if any command returns with non-zero exit status (aka failure)
set -e

# modify this line to run your desired Python script and any other work you need to do
python3 nestCamAnalysis.py $1