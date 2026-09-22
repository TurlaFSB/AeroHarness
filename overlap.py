import json, csv, re

csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv"
}
for name, p in csv_files.items():
    print(f"--- {name} CSV ---")
    with open(p) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "MCG" in row["Reg name"]:
                print(row["Reg name"])
