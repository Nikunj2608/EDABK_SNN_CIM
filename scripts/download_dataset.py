import os
from spikingjelly.datasets.dvs128_gesture import DVS128Gesture

# Go up one level from the 'scripts' folder, into the 'data' folder
dataset_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'dvs128_raw')

if not os.path.exists(dataset_dir):
    os.makedirs(dataset_dir)

print("Starting DVS128 Gesture Dataset Download...")
print(f"Saving to: {os.path.abspath(dataset_dir)}")
print("This is a 3-5 GB download. Let this run overnight!")

# This downloads the Train and Test sets automatically
train_set = DVS128Gesture(dataset_dir, train=True, data_type='event')
test_set = DVS128Gesture(dataset_dir, train=False, data_type='event')

print("\n✅ Download Complete!")