#!/bin/bash

# untar your Python installation. Make sure you are using the right version!
#tar -xzf python39.tar.gz
# (optional) if you have a set of packages (created in Part 1), untar them also
#tar -xzf wranglePrep2.tar.gz
cp /staging/ttang53/$1 .

# make sure the script will use your Python installation, 
# and the working directory as its home location
export PATH=$PWD/python/bin:$PATH
export PYTHONPATH=$PWD/packages
export HOME=$PWD

# have job exit if any command returns with non-zero exit status (aka failure)
set -e

# replace env-name on the right hand side of this line with the name of your conda environment
ENVNAME=tracpaths
# if you need the environment directory to be named something other than the environment name, change this line
ENVDIR=$ENVNAME

# these lines handle setting up the environment; you shouldn't have to modify them
export PATH
mkdir $ENVDIR
tar -xzf $ENVNAME.tar.gz -C $ENVDIR
. $ENVDIR/bin/activate

# modify this line to run your desired Python script and any other work you need to do
mv wranglePrep2/* .
python3 wranglePrep.py $1