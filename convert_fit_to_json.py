import fitparse
import json
import sys
from datetime import datetime

def custom_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)

filename = sys.argv[1]
fitfile = fitparse.FitFile(filename)

output_data = {}

for msg in fitfile.get_messages():
    # Skip entirely unknown message types
    if msg.name is None or msg.name.startswith('unknown_'):
        continue

    msg_name = msg.name
    if msg_name not in output_data:
        output_data[msg_name] = []
    
    msg_dict = {}
    for data in msg:
        # Skip unknown fields within known message types
        if data.name is not None and not data.name.startswith('unknown_'):
            msg_dict[data.name] = data.value
            
    # Only append if we actually extracted meaningful data
    if msg_dict:
        output_data[msg_name].append(msg_dict)

out_name = filename.replace('.FIT', '.json').replace('.fit', '.json')

with open(out_name, 'w') as f:
    json.dump(output_data, f, default=custom_serializer, indent=2)

