#!/bin/bash

# Create directories if they do not exist
mkdir -p /app/data/databases
mkdir -p /app/data/logs

# Start the bot script
python bot.py
