#!/bin/bash

# Exit immediately if a command fails
set -e

echo "Creating virtual environment with Python 3.11..."
/opt/homebrew/bin/python3.11 -m venv .venv

source .venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    echo "No requirements.txt found. Skipping dependency installation."
fi

# echo "Running batch run..."
# python3 batch_run.py

# echo "Generating fidelity plots..."
# python3 generate_visuals.py

echo "Clustering..."
python3 modules/clustering.py