import numpy as np
import os

def generate_verilog_stimuli(npz_file, output_file, num_frames=10, dt_us=50000):
    print(f"Loading raw DVS data from: {npz_file}")
    
    # Load the event data
    events = np.load(npz_file)
    t, x, y = events['t'], events['x'], events['y']

    # 1. Downsample 128x128 -> 32x32 to fit the SNN crossbar
    x_ds = np.clip(x // 4, 0, 31)
    y_ds = np.clip(y // 4, 0, 31)

    print(f"Extracting {num_frames} frames ({dt_us/1000}ms each)...")
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w') as f:
        for frame_idx in range(num_frames):
            # Define the time window for this specific frame
            t_start = t[0] + frame_idx * dt_us
            t_end = t_start + dt_us

            # Filter out the events that happened in this exact window
            mask = (t >= t_start) & (t < t_end)
            x_frame = x_ds[mask]
            y_frame = y_ds[mask]

            # 2. Create the 32x32 binary image (1 if spike occurred, 0 if silent)
            spike_matrix = np.zeros((32, 32), dtype=int)
            spike_matrix[y_frame, x_frame] = 1 

            # 3. Write to file in standard Verilog binary format
            f.write(f"// --- Frame {frame_idx} (t={t_start} to {t_end}) ---\n")
            for row in range(32):
                # Convert the numpy array row into a 32-bit string like "00100011..."
                bin_str = "".join(str(val) for val in spike_matrix[row])
                f.write(f"{bin_str}\n")

    print(f"✅ Hardware stimuli successfully saved to: {output_file}")

# Execution: Let's test it on Class 2 (Left Arm Clockwise)
input_npz = os.path.join(os.path.dirname(__file__), '..', 'data', 'dvs128_raw', 'events_np', 'test', '2', 'user29_lab_0.npz')
output_txt = os.path.join(os.path.dirname(__file__), '..', 'verilog', 'tb', 'stimuli_class2.txt')

generate_verilog_stimuli(input_npz, output_txt)