import fitparse
import sys
from collections import Counter

filename = sys.argv[1]
fitfile = fitparse.FitFile(filename)

# Count all message types
message_counts = Counter()
for msg in fitfile.get_messages():
    message_counts[msg.name] += 1

print(f"--- Message Types in {filename.split('/')[-1]} ---")
for name, count in message_counts.most_common():
    print(f"{name}: {count}")

print("\n--- Structured Workout Steps ---")
workout_steps = list(fitfile.get_messages('workout_step'))
if not workout_steps:
    print("No 'workout_step' messages found in this file.")
else:
    for i, step in enumerate(workout_steps):
        print(f"Step {i+1}:")
        for data in step:
            if data.value is not None:
                print(f"  {data.name}: {data.value} {data.units if data.units else ''}")
        print()

print("\n--- Lap Data (Actual completed intervals) ---")
laps = list(fitfile.get_messages('lap'))
if not laps:
    print("No 'lap' messages found.")
else:
    for i, lap in enumerate(laps):
        time = None
        intensity = "active"
        for data in lap:
            if data.name == 'total_elapsed_time': time = data.value
            if data.name == 'intensity': intensity = data.value
        print(f"Lap {i+1}: {time}s, Intensity: {intensity}")

