#!/bin/bash
# Just a quick caller for batch-testing

echo Command
python3 UT_Command.py

echo File
python3 UT_File.py

echo Checksum
python3 UT_Checksum.py

echo Encryption
python3 UT_Encryption.py

echo Tape
python3 UT_Tape.py
