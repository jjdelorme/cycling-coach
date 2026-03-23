import fitparse
import pandas as pd
import sys

filename = sys.argv[1]
fitfile = fitparse.FitFile(filename)

# We are specifically extracting the 'record' messages, which contain 
# the time-series data of the workout (heart rate, power, speed, position, etc.)
records = []
for record in fitfile.get_messages('record'):
    data = {}
    for record_data in record:
        data[record_data.name] = record_data.value
    records.append(data)

df = pd.DataFrame(records)
out_name = filename.replace('.FIT', '.csv')
df.to_csv(out_name, index=False)
print(f"Successfully converted:\n{filename}\n-> {out_name}")
print(f"Total data points: {len(df)}")
