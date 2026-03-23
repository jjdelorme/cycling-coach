import fitparse
import glob
import sys

files = glob.glob("/home/jasondel/dev/coach/*.FIT")
found = 0

print(f"Scanning {len(files)} FIT files for structured workout data...")

for f in files:
    try:
        fitfile = fitparse.FitFile(f)
        steps = list(fitfile.get_messages('workout_step'))
        if steps:
            print(f"Found {len(steps)} workout steps in: {f.split('/')[-1]}")
            found += 1
            if found <= 1: # Only print details for the first one found
                print("Example Step Data:")
                for i, step in enumerate(steps[:3]): # print first 3 steps
                    print(f"  Step {i+1}:")
                    for data in step:
                        if data.value is not None:
                            print(f"    {data.name}: {data.value} {data.units if data.units else ''}")
    except Exception as e:
        pass # skip files that fail to parse

print(f"\nFound structured 'workout_step' data in {found} out of {len(files)} files.")
