#!/bin/bash

# Anzahl der Dateien
NUM_FILES=10

# Minimal- und Maximalgrößen in Bytes
MIN_SIZE=$((1 * 1024 * 1024))   # 1 MB
MAX_SIZE=$((2 * 1024 * 1024 * 1024)) # 2 GB

echo "Erstelle $NUM_FILES Testdateien im aktuellen Verzeichnis..."

for i in $(seq 1 $NUM_FILES); do
  # Generiere eine zufällige Dateigröße zwischen MIN_SIZE und MAX_SIZE
  FILE_SIZE=$((RANDOM * RANDOM % (MAX_SIZE - MIN_SIZE + 1) + MIN_SIZE))
  
  # Generiere Dateinamen
  FILE_NAME="testfile_$i.bin"
  
  # Erstelle die Datei mit zufälligen Daten
  echo "Erstelle $FILE_NAME mit Größe $(($FILE_SIZE / 1024 / 1024)) MB..."
  dd if=/dev/urandom of="./testfiles/$FILE_NAME" bs=1M count=$(($FILE_SIZE / 1024 / 1024)) iflag=fullblock status=none
done

echo "Fertig! $NUM_FILES Dateien erstellt."