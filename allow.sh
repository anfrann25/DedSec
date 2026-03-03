# Φτιάξε μια λίστα αρχείων που ΔΕΝ θα αγγίξουμε
printf "Scripts/Fake Pages\nScripts/Personal Information Capture\n" > PORT_EXCLUDE.txt

# Φτιάξε λίστα αρχείων που θα επιτρέπεται να τρέχουν στο Linux build (πρώτο draft)
find Scripts/Games Scripts/Developer\ Base -type f -name "*.py" | sort > PORT_ALLOW.txt

wc -l PORT_ALLOW.txt PORT_EXCLUDE.txt