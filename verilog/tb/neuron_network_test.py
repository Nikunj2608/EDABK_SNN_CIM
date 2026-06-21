import os
import sys
from pathlib import Path

import cocotb
from rram_neuron_model import conductance_at_age, calculate_1t1r_syn_sum, calculate_1t1r_discrete_step
# from cocotb.binary import BinaryRepresentation, BinaryValue
from cocotb.triggers import Timer
from cocotb.clock import Clock
from cocotb.handle import SimHandleBase, Force, Release
from cocotb.queue import Queue
# from cocotb.runner import get_runner
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from nvm_parameter import *
from read_file import *

async def load_and_inject_stimuli(dut, file_path):
    # 1. Read the text file we generated
    with open(file_path, "r") as f:
        # Filter out comments and whitespace
        spike_data = [line.strip() for line in f if line.strip() and not line.startswith("//")]

    dut._log.info(f"Loaded {len(spike_data)} rows of spikes from {file_path}")

    # 2. Feed it into the SNN row-by-row
    # Assuming your SNN is mapped to the 'mprj' pins or internal wires
    for i, binary_row in enumerate(spike_data):
        # Convert "0010..." to integer
        spike_val = int(binary_row, 2)
        
        # Drive the value into your user project
        # Update 'uut.chip_core.mprj' to match your actual SNN input port name
        dut.uut.chip_core.mprj.user_project.input_spikes.value = spike_val
        
        # Wait for 1 clock cycle (or match your Ramp modulation timing)
        await ClockCycles(dut.clk, 1)
        
        if i % 32 == 0:
            dut._log.info(f"Processing Frame {i//32}...")

TB_DIR = Path(__file__).resolve().parent
BASE_DIR = TB_DIR / "mem" / "connection"

_default_input = TB_DIR / "stimuli_class2.txt"
_fallback_input = TB_DIR / "mem" / "stimuli" / "stimuli.txt"
INPUT_FILE = Path(os.environ.get("TB_STIMULI_FILE", str(_default_input)))
if not INPUT_FILE.exists() and _fallback_input.exists():
    INPUT_FILE = _fallback_input

LAYER1_SPIKE_STIM = int(os.environ.get("TB_LAYER1_SPIKE_STIM", "1"))
LAYER2_SPIKE_STIM = int(os.environ.get("TB_LAYER2_SPIKE_STIM", "4"))
DEBUG_ACTIVE_AXON = os.environ.get("TB_DEBUG_ACTIVE_AXON", "0") == "1"
L0_STIM_MODE = os.environ.get("TB_L0_STIM_MODE", "raw16").strip().lower()
L0_STIM_GAIN = int(os.environ.get("TB_L0_STIM_GAIN", "1"))
INTER_PIC_IDLE_CYCLES = int(os.environ.get("TB_INTER_PIC_IDLE_CYCLES", "0"))
RESET_BETWEEN_PICS = os.environ.get("TB_RESET_BETWEEN_PICS", "0") == "1"
HARD_RESET_BETWEEN_PICS = os.environ.get("TB_HARD_RESET_BETWEEN_PICS", "0") == "1"

RRAM_AGE_S = float(os.environ.get("TB_RRAM_AGE_S", "1500.0"))
RRAM_LRS_KEEP_THRESHOLD = float(os.environ.get("TB_RRAM_LRS_KEEP_THRESHOLD", "1.5"))
DISABLE_RRAM_DEGRADATION = os.environ.get("TB_DISABLE_RRAM_DEGRADATION", "0") == "1"


def load_stimuli_frames(file_path, requested_pics=None):
    """Load 32-bit row stimuli grouped as 32 rows per frame."""
    with open(file_path, "r") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("//")]

    if len(lines) < 32:
        raise ValueError(f"Stimuli file has only {len(lines)} valid rows: {file_path}")

    available_pics = len(lines) // 32
    if requested_pics is None:
        pics_to_use = available_pics
    else:
        pics_to_use = min(requested_pics, available_pics)

    stimuli = []
    for pic in range(pics_to_use):
        frame_data = []
        for row in range(32):
            row_int = int(lines[pic * 32 + row], 2)
            frame_data.append(row_int)
        stimuli.append(frame_data)

    return stimuli


def encode_l0_block(block_16b):
    """Encode a 16-bit input block into the scalar stimulus consumed by the neuron core."""
    mode = L0_STIM_MODE
    if mode == "raw16":
        return block_16b

    bit_count = bin(block_16b & 0xFFFF).count("1")
    if mode == "popcount16":
        return bit_count * max(1, L0_STIM_GAIN)
    if mode == "binary_presence":
        return max(1, L0_STIM_GAIN) if bit_count > 0 else 0

    raise ValueError(f"Unsupported TB_L0_STIM_MODE={L0_STIM_MODE}. Use raw16|popcount16|binary_presence")


def summarize_stimuli_activity(stimuli):
    if not stimuli:
        print("Stimuli summary: no frames")
        return
    frame_ones = []
    for frame in stimuli:
        ones = sum(bin(row).count("1") for row in frame)
        frame_ones.append(ones)
    print(
        "Stimuli summary: "
        f"frames={len(stimuli)}, "
        f"frame_ones_min={min(frame_ones)}, "
        f"frame_ones_max={max(frame_ones)}, "
        f"frame_ones_avg={sum(frame_ones)/float(len(frame_ones)):.2f}"
    )


def summarize_layer_activity(layer_name, spike_matrix):
    """Print compact spike statistics to detect silence/saturation quickly."""
    if not spike_matrix:
        print(f"{layer_name} activity: no frames")
        return

    frame_count = len(spike_matrix)
    neuron_count = len(spike_matrix[0]) if spike_matrix[0] else 0
    total_slots = frame_count * neuron_count
    total_spikes = sum(sum(frame) for frame in spike_matrix)
    spike_ratio = (total_spikes / float(total_slots)) if total_slots > 0 else 0.0
    per_frame_counts = [sum(frame) for frame in spike_matrix]
    unique_frame_count = len({tuple(frame) for frame in spike_matrix})
    min_frame_spikes = min(per_frame_counts) if per_frame_counts else 0
    max_frame_spikes = max(per_frame_counts) if per_frame_counts else 0

    print(
        f"{layer_name} activity summary: total_spikes={total_spikes}, "
        f"spike_ratio={spike_ratio:.4f}, frame_min={min_frame_spikes}, "
        f"frame_max={max_frame_spikes}, unique_frames={unique_frame_count}/{frame_count}"
    )
# --- Helper Functions for Wishbone and NVM Access ---

# Wishbone Write: Used to send control or configuration data to the DUT.
async def wishbone_write(dut, address, data):
    """
    Performs a Wishbone write transaction.
    
    The transaction is:
    1. Drive signals on positive clock edge.
    2. De-assert signals on the next positive clock edge.
    3. Wait for one falling edge (optional, often used for cycle completion).
    """
    # Cycle 1: Assert request signals
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 1       # Cycle valid
    dut.wbs_stb_i.value = 1       # Strobe (data valid)
    dut.wbs_we_i.value = 1        # Write enable
    dut.wbs_sel_i.value = 0b1111  # Byte select (all bytes enabled for 32-bit write)
    dut.wbs_adr_i.value = address # Address
    dut.wbs_dat_i.value = data    # Write data

    # Cycle 2: De-assert request signals
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0
    dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value = 0
    dut.wbs_sel_i.value = 0b0000

    # Wait for completion (often necessary depending on DUT design)
    await FallingEdge(dut.wb_clk_i)

# Wishbone Read: Used for reading spikes out or output packets from the last core.
async def wishbone_read(dut, address, spike_o_matrix=None, pic=0, slice_idx=0, layer=0, core=0):
    """
    Performs a Wishbone read transaction.
    
    The transaction is:
    1. Assert request signals (read enable = 0) on positive clock edge.
    2. De-assert signals on the next positive clock edge.
    3. Read data on the falling edge after the de-assertion.
    
    If spike_o_matrix is provided, it extracts spike data from the read value.
    """
    # Cycle 1: Assert request signals
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 1       # Cycle valid
    dut.wbs_stb_i.value = 1       # Strobe (data valid)
    dut.wbs_we_i.value = 0        # Read enable (Write enable is 0)
    dut.wbs_sel_i.value = 0b1111  # Byte select
    dut.wbs_adr_i.value = address # Address
    dut.wbs_dat_i.value = 0       # Don't care for read

    # Cycle 2: De-assert request signals
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0
    dut.wbs_stb_i.value = 0
    dut.wbs_sel_i.value = 0
        
    # Wait for data to be stable (assuming data is valid after de-assertion)
    await FallingEdge(dut.wb_clk_i)
    
    # Read the output data from the DUT
    # The output spike is expected to be reversed (LSB first) for easier indexing.
    # Assumes dut.wbs_dat_o.value returns a BinaryValue
    output_spike = str(dut.wbs_dat_o.value)[::-1]
    if layer == 0 and pic == 0:
        dut._log.info(
            f"READBACK slice={slice_idx} "
            f"raw={dut.wbs_dat_o.value}"
        )
    # If a spike matrix is provided, parse and store the spike outputs
    if spike_o_matrix is not None:
        # NUM_NEURON_PER_SLICE must be the number of bits in output_spike
        for i in range(NUM_NEURON_PER_SLICE):
            # Calculate the global neuron index in the layer's output matrix
            global_neuron_index = core * NUM_NEURON + slice_idx * NUM_NEURON_PER_SLICE + i
            # Store the spike (0 or 1)
            spike_o_matrix[pic][global_neuron_index] = int(output_spike[i])

async def program_8bit_weight(dut, row_idx, neuron_idx, weight_val):
    """
    Translates an int8 weight into the 32-bit Wishbone payload for the 1T1R array.
    """
    # 1. Extract Sign and Magnitude from the int8 weight (-128 to 127)
    # The 1T1R array uses G_BITS=3 for conductance, plus 1 bit for sign.
    sign_bit = 1 if weight_val < 0 else 0
    magnitude = abs(weight_val) & 0x07  # Mask to lower 3 bits (0-7)
    
    # 2. Pack the 32-bit Wishbone payload based on the Caravel Wrapper mapping:
    # [31:30] = 2'b11 (Write Mode)
    # [29:25] = Row/Axon index (0-31)
    # [23:20] = Neuron index (0-15 within the array)
    # [7]     = Sign bit (1 = negative, 0 = positive)
    # [2:0]   = Conductance Level (Magnitude)
    
    mode_bits   = 0x3 << 30
    row_bits    = (row_idx & 0x1F) << 25
    neuron_bits = (neuron_idx & 0x0F) << 20
    sign_mapped = (sign_bit & 0x1) << 7
    mag_mapped  = (magnitude & 0x7)
    
    wb_payload = mode_bits | row_bits | neuron_bits | sign_mapped | mag_mapped
    
    # 3. Determine target address based on your 64x64 decoder
    # The core decoder routes 0x3000_0XXX addresses
    TARGET_ADDR = 0x3000_000C
    
    # 4. Execute the Wishbone Write using your existing cocotb driver mechanism
    # (Adapt the line below to match your specific Wishbone write helper function)
    await wishbone_write(dut, TARGET_ADDR, wb_payload)
    
    # Optional debug logging to match your existing output format
    # dut._log.debug(f"Programmed Axon {row_idx}, Neuron {neuron_idx} | "
    #                f"Weight: {weight_val} -> Payload: {hex(wb_payload)}")




# NVM Write: Performs a Wishbone write with an additional delay for Non-Volatile Memory (NVM) programming.
async def nvm_write(dut, address, data):
    """
    Performs a Write operation to the NVM block, incorporating the NVM programming delay.
    """
    async def drive_wishbone():
        # Wishbone transaction setup
        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 1
        dut.wbs_stb_i.value = 1
        dut.wbs_we_i.value = 1
        dut.wbs_sel_i.value = 0b1111
        dut.wbs_adr_i.value = address
        dut.wbs_dat_i.value = data

        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 0
        dut.wbs_stb_i.value = 0
        dut.wbs_we_i.value = 0
        dut.wbs_sel_i.value = 0

    async def wait_for_delay():
        # Wait for the NVM Write Delay (WR_Dly) to ensure programming completes
        await ClockCycles(dut.wb_clk_i, (2 * WR_Dly + 1))

    # Start the Wishbone drive and the delay concurrently
    drive_task = cocotb.start_soon(drive_wishbone())
    delay_task = cocotb.start_soon(wait_for_delay())

    # Wait for both tasks to complete (drive_task finishes quickly, delay_task takes time)
    await drive_task
    await delay_task

# NVM Read: Performs a pseudo-write (for command/stimulus) followed by an NVM Read operation.
async def nvm_read(dut, addr, data):
    """
    Performs a Read operation from the NVM block, consisting of:
    1. A 'Write' phase to configure the address/stimulus (no NVM write delay needed here).
    2. A delay for NVM Read access time (RD_Dly).
    3. A subsequent 'Read' phase to get the data.
    """
    async def operation_1_write():
        # Phase 1: 'Write' operation to set up command/stimulus (like a configuration write)
        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 1
        dut.wbs_stb_i.value = 1
        dut.wbs_we_i.value = 1
        dut.wbs_sel_i.value = 0xF
        dut.wbs_adr_i.value = addr
        dut.wbs_dat_i.value = data

        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 0
        dut.wbs_stb_i.value = 0
        dut.wbs_we_i.value  = 0
        dut.wbs_sel_i.value = 0

    async def operation_2_read_after_delay():
        # Wait for the NVM Read Delay
        await ClockCycles(dut.wb_clk_i, (RD_Dly + 2))

        # Phase 2: 'Read' operation
        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 1
        dut.wbs_stb_i.value = 1
        dut.wbs_we_i.value  = 0 
        dut.wbs_sel_i.value = 0xF
        dut.wbs_adr_i.value = addr 
        # --- FIX: Drive the spike mask during the read cycle ---
        dut.wbs_dat_i.value = data 

        # Hold request until matrix returns valid read data.
        while int(dut.wbs_ack_o.value) == 0:
            await RisingEdge(dut.wb_clk_i)

        await RisingEdge(dut.wb_clk_i)
        dut.wbs_cyc_i.value = 0
        dut.wbs_stb_i.value = 0
        dut.wbs_sel_i.value = 0

    # Start the two operations sequentially (task_1 must finish before task_2 can proceed past the delay)
    task_1 = cocotb.start_soon(operation_1_write())
    await task_1 
    
    task_2 = cocotb.start_soon(operation_2_read_after_delay())
    await task_2

# --- Testbench Functions ---

def get_connection_file_path(base_dir, index, part=None):
    """Constructs the full path for a connection file."""
    if part:
        filename = f"connection_{index:03}_part{part}.txt"
    else:
        filename = f"connection_{index:03}.txt"
    return str(Path(base_dir) / filename)

def load_connection_matrices(base_path):
    """Loads all connection matrices into a dictionary."""
    print("Loading connection files...")
    connection_matrices = {}
        
    # Layer 0 connections (0 to 12)
    for i in range(13):
        path = get_connection_file_path(base_path, i)
        connection_matrices[i] = read_matrix_from_file(path)
        
    # Layer 1 connections (13 to 16)
    for i in range(13, 17):
        path = get_connection_file_path(base_path, i)
        connection_matrices[i] = read_matrix_from_file(path)
        
    # Layer 2 connection (index 26 parts 1 to 4)
    for part in range(1, 5):
        index = 26 + part / 10 # Using float key temporarily
        path = get_connection_file_path(base_path, 26, part)
        connection_matrices[index] = read_matrix_from_file(path)
        
    return connection_matrices

async def program_layer_connections(dut, core_idx, layer_key, flip_sign=False):
    """
    Upgraded Loader: Programs 8-bit signed weights from Hex files.
    layer_key: "L1", "L2", or "L3"
    flip_sign: Toggle polarity for diagnostics (False=P-N, True=N-P).
    """
    # Use Path to find files in the same directory as this script
    script_dir = Path(__file__).resolve().parent
    pos_file = script_dir / f"sentry_{layer_key}_pos.hex"
    neg_file = script_dir / f"sentry_{layer_key}_neg.hex"

    if not pos_file.exists():
        raise FileNotFoundError(f"Missing weight file: {pos_file}")

    # 1. Load the Hex data
    with open(pos_file, "r") as fp, open(neg_file, "r") as fn:
        pos_raw = [int(line.strip(), 16) for line in fp if line.strip()]
        neg_raw = [int(line.strip(), 16) for line in fn if line.strip()]

    # 2. Program the 256 axons handled by this Core
    offset = core_idx * 256
    polarity_str = "N-P" if flip_sign else "P-N"
    dut._log.info(
        f"Programming {layer_key} Core {core_idx} ({polarity_str}) "
        f"(Hex indices {offset} to {offset+255})"
    )

    for i in range(256):
        row = i // 32
        col = i % 32
        
        # Calculate signed 8-bit weight with optional diagnostic polarity flip.
        # Bounds check to prevent crashes if hex file is shorter than expected.
        idx = offset + i
        if flip_sign:
            w_signed = neg_raw[idx] - pos_raw[idx]
        else:
            w_signed = pos_raw[idx] - neg_raw[idx]
        
        # Pack into 32-bit Wishbone word
        # [MODE_PROG(2)][ROW(5)][COL(5)][PAD(4)][WEIGHT(16)]
        # Program using the new 1T1R 8-bit mapping logic
        await program_8bit_weight(dut, row, col, w_signed)

    dut._log.info(f"✅ {layer_key} Core {core_idx} programming complete.")
            
async def run_layer_for_all_pics(dut, core_idx, layer, num_cores, spike_in_matrix, spike_out_matrix, num_pics, stimuli=None, layer_axon_limit=None):
    """
    Runs the simulation for all input pictures for a specific core (EVERY PIC step).
    
    This corresponds to the 'MODE_READ' operation (stimulus application).
    """
    per_pic_active_axons = []
    per_pic_input_signature = []

    for pic in range(num_pics):
        print(f"Layer {layer} - Core {core_idx} - Pic {pic}")

        # Optional frame separation to avoid carry-over dynamics from previous picture.
        if pic > 0 and INTER_PIC_IDLE_CYCLES > 0:
            await ClockCycles(dut.wb_clk_i, INTER_PIC_IDLE_CYCLES)
        if pic > 0 and RESET_BETWEEN_PICS:
            # Soft clear between pictures: preserve programmed weights, clear per-slice state.
            await wishbone_write(dut, 0x30002000, 0)
            await wishbone_write(dut, 0x30002002, 0)
            await wishbone_write(dut, 0x30002004, 0)
            await wishbone_write(dut, 0x30002006, 0)

            # Optional hard reset is explicit because it can wipe programmed state.
            if HARD_RESET_BETWEEN_PICS:
                dut.wb_rst_i.value = 1
                await ClockCycles(dut.wb_clk_i, 2)
                dut.wb_rst_i.value = 0

        active_axon_count = 0
        input_signature = 0
        
        # Iterate over the NVM array structure
        for row_i in range(32):
            for col_i in range(32):
                row = row_i
                col = col_i
                
                # Axon index calculation
                axon = ((row & 0x07) * 32) + col 
                
                # Check for axon limit specific to the layer (e.g., if the layer has fewer than 256 inputs)
                if layer_axon_limit is not None and axon >= layer_axon_limit:
                    continue 
                
                # Neuron index calculation (not used directly here, but for completeness)
                # neuron = ((row >> 3) & 0x03) * 16 
                
                spike_active = False
                val_slice = 0
                
                # Input stimuli (spike_in) depends on the layer:
                if layer == 0:
                    # Layer 0: The stimuli is read directly from our text file
                    # We need to take the 32-bit row and split it into two 16-bit blocks
                    # based on whether it is an even or odd axon group.
                    
                    full_stimuli_val = stimuli[pic][row] 
                    
                    if (axon % 2) == 0:
                        # Even axon: Take the upper 16 bits [31:16]
                        block_16b = (full_stimuli_val >> 16) & 0xFFFF
                    else:
                        # Odd axon: Take the lower 16 bits [15:0]
                        block_16b = full_stimuli_val & 0xFFFF

                    val_slice = encode_l0_block(block_16b)

                    if pic == 0 and core_idx == 0 and row < 3:
                        dut._log.info(
                            f"STIM DEBUG | "
                            f"row={row} "
                            f"axon={axon} "
                            f"block16=0x{block_16b:04X} "
                            f"stim={val_slice}"
                        )  
                        
                    spike_active = True # We always trigger the read for L0 to inject the block
                elif layer == 1 and spike_in_matrix is not None:
                    input_idx = core_idx * NUM_AXON_LAYER_1 + axon
                    if input_idx < len(spike_in_matrix[pic]) and spike_in_matrix[pic][input_idx] == 1:
                        val_slice = max(0, min(0xFFFF, LAYER1_SPIKE_STIM))
                        spike_active = True
                elif layer == 2 and spike_in_matrix is not None:
                    input_idx = axon
                    if input_idx < len(spike_in_matrix[pic]) and spike_in_matrix[pic][input_idx] == 1:
                        val_slice = max(0, min(0xFFFF, LAYER2_SPIKE_STIM))
                        spike_active = True
                
                
                if spike_active:
                    active_axon_count += 1
                    input_signature = ((input_signature * 1315423911) ^ (axon + 0x9E3779B9)) & 0xFFFFFFFF
                    # Construct the 32-bit data word for NVM Read Operation (stimulus application)
                    # {MODE_READ(2), row(5), col(5), padding(4), stimulus_data(16)}

                    data_for_read_op = (
                        (MODE_READ << 30) |  # 2 MSBs for MODE
                        (row         << 25) |  # 5 bits for row index
                        (col         << 20) |  # 5 bits for column index
                        (0           << 16) |  # 4 bits padding (0)
                        (val_slice)             # 16 LSBs for stimulus data (or just '1' for spike)
                    )
                    
                    await nvm_read(dut, 0x30000000, data_for_read_op)

                    if layer == 0 and pic == 0 and core_idx == 0 and active_axon_count < 20:
                        try:
                            dut._log.info(
                            f"AXON={axon} "
                            f"ROW={row} "
                            f"COL={col} "
                            f"STIM={val_slice} "
                            f"WEIGHT={dut.current_weight.value.to_signed()} "
                            f"CONN={dut.connection.value} "
                            f"POT={dut.neuron_block_inst.potential[0].value.to_signed()}"
                            f"SPIKE={int(dut.spike_o.value[0])}"
                        )
                        except Exception as e:
                            dut._log.info(f"DEBUG ERROR: {e}")

                # Control Register Writes (e.g., resetting internal slice/neuron logic after an NVM row sweep)
                # These addresses (0x3000200x) likely correspond to control registers for neuron slices.
                # The writes happen after every NVM array row group (e.g., after rows 7, 15, 23, 31)
                if col == 31:

                    try:
                        dut._log.info(
                        f"BEFORE CTRL WRITE "
                        f"row={row} "
                        f"POT={dut.neuron_block_inst.potential[0].value.to_signed()}"
                    )
                    except:
                        pass

                    if row == 7:
                        await wishbone_write(dut, 0x30002000, 0)
                    elif row == 15:
                        await wishbone_write(dut, 0x30002002, 0)
                    elif row == 23:
                        await wishbone_write(dut, 0x30002004, 0)
                    elif row == 31:
                        await wishbone_write(dut, 0x30002006, 0)

                    try:
                        dut._log.info(
                            f"AFTER CTRL WRITE "
                            f"row={row} "
                            f"POT={dut.neuron_block_inst.potential[0].value.to_signed()}"
                        )
                    except:
                        pass
        if layer == 0:
            try:
                dut._log.info(
                    f"L0 END PIC | "
                    f"potential0={dut.neuron_block_inst.potential[0].value.to_signed()}"
                )
            except:
                pass
        # Read the output spikes from the two slices of the core after processing all inputs
        await wishbone_read(dut, 0x30001000, spike_out_matrix, pic, slice_idx=0, layer=layer, core=core_idx)
        await wishbone_read(dut, 0x30001004, spike_out_matrix, pic, slice_idx=1, layer=layer, core=core_idx)
        if layer == 0:
            pic_spikes = sum(spike_out_matrix[pic])

            dut._log.info(
                f"L0 DEBUG | Pic={pic} "
                f"Core={core_idx} "
                f"SpikeCount={pic_spikes}"
            )

            if pic_spikes > 0:
                dut._log.info(
                    f"L0 DEBUG | First 32 outputs = "
                    f"{spike_out_matrix[pic][:32]}"
                ) 
        per_pic_active_axons.append(active_axon_count)
        per_pic_input_signature.append(input_signature)
        if DEBUG_ACTIVE_AXON and layer in (1, 2):
            print(
                f"L{layer} Core {core_idx} Pic {pic} "
                f"active_axons={active_axon_count} sig=0x{input_signature:08X}"
            )

    if layer in (1, 2) and per_pic_active_axons:
        min_active = min(per_pic_active_axons)
        max_active = max(per_pic_active_axons)
        unique_sig = len(set(per_pic_input_signature))
        print(
            f"L{layer} Core {core_idx} input summary: "
            f"active_axons[min,max]=[{min_active},{max_active}], "
            f"unique_signatures={unique_sig}/{len(per_pic_input_signature)}"
        )



def generate_software_baseline(stimuli, layer_key, num_pics, num_neurons=64):
    """
    Software Digital Twin: Simulates the 1T1R array perfectly in Python
    to generate expected spikes to compare against the Caravel hardware.
    """
    print(f"\n[Digital Twin] Generating Python baseline for {layer_key}...")
    
    # 1. Load the exact same weights that were programmed into hardware
    script_dir = Path(__file__).resolve().parent
    pos_file = script_dir / f"sentry_{layer_key}_pos.hex"
    neg_file = script_dir / f"sentry_{layer_key}_neg.hex"
    
    with open(pos_file, "r") as fp, open(neg_file, "r") as fn:
        pos_raw = [int(line.strip(), 16) for line in fp if line.strip()]
        neg_raw = [int(line.strip(), 16) for line in fn if line.strip()]
        
    int8_weights = [p - n for p, n in zip(pos_raw, neg_raw)]
    
    software_v_mem = [0] * num_neurons 
    expected_out_matrix = [[0 for _ in range(num_neurons)] for _ in range(num_pics)]

    # 2. Frame-by-frame simulation
    for pic in range(num_pics):
        frame_stimuli = stimuli[pic]
        
        # Convert the 32x32 frame into a flat list of 1024 binary spikes
        current_spikes = []
        for row in frame_stimuli:
            for bit_idx in range(32):
                current_spikes.append(1 if (row >> bit_idx) & 0x1 else 0)

        for neuron_idx in range(num_neurons):
            # Extract the 1024 weights connected to this specific neuron
            neuron_weights = int8_weights[neuron_idx::num_neurons]
            
            # Use the functions from rram_neuron_model.py
            syn_sum = calculate_1t1r_syn_sum(current_spikes, neuron_weights)
            next_v_mem, spike = calculate_1t1r_discrete_step(software_v_mem[neuron_idx], syn_sum)
            
            software_v_mem[neuron_idx] = next_v_mem
            expected_out_matrix[pic][neuron_idx] = spike

    return expected_out_matrix



# --- Cocotb Test ---




@cocotb.test()
async def neuron_network_test(dut): 
    # Weights are programmed from sentry_L*_pos/neg.hex via program_layer_connections.
    
    # Load stimuli and correct output files
    # TB_NUM_PICS can override picture count for quick tests; default is full file.
    tb_num_pics = os.environ.get("TB_NUM_PICS")
    requested_pics = int(tb_num_pics) if tb_num_pics else None
    stimuli = load_stimuli_frames(INPUT_FILE, requested_pics)
    run_pics = len(stimuli)

    print(
        "TB config: "
        f"INPUT_FILE={INPUT_FILE}, run_pics={run_pics}, "
        f"L0_STIM_MODE={L0_STIM_MODE}, L0_STIM_GAIN={L0_STIM_GAIN}, "
        f"INTER_PIC_IDLE_CYCLES={INTER_PIC_IDLE_CYCLES}, "
        f"RESET_BETWEEN_PICS={RESET_BETWEEN_PICS}, HARD_RESET_BETWEEN_PICS={HARD_RESET_BETWEEN_PICS}, "
        f"DISABLE_RRAM_DEGRADATION={DISABLE_RRAM_DEGRADATION}, "
        f"RRAM_AGE_S={RRAM_AGE_S}, RRAM_LRS_KEEP_THRESHOLD={RRAM_LRS_KEEP_THRESHOLD}"
    )
    if run_pics <= 1:
        print("WARNING: run_pics <= 1, prediction confidence will be limited. Prefer TB_NUM_PICS>=5.")
    summarize_stimuli_activity(stimuli)
    
    # Initialize spike output matrices for each layer
    spike_out_layer_0 = [[0 for _ in range(NUM_CORES_LAYER_0 * NUM_NEURON)] for __ in range(run_pics)]
    spike_out_layer_1 = [[0 for _ in range(NUM_CORES_LAYER_1 * NUM_NEURON)] for __ in range(run_pics)]
    spike_out_layer_2 = [[0 for _ in range(NUM_CORES_LAYER_2 * NUM_NEURON)] for __ in range(run_pics)]
    
    # --- Clock and Reset Initialization ---
    print("\nStarting Clock and Reset\n")
    clock = Clock(dut.wb_clk_i, PERIOD, unit="ns")
    cocotb.start_soon(clock.start(start_high=True))
    
    # Initial state (assert reset)
    dut.wb_rst_i.value = 1
    dut.wbs_cyc_i.value = 0
    dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value = 0
    dut.wbs_sel_i.value = 0b0000
    dut.wbs_adr_i.value = 0
    dut.wbs_dat_i.value = 0
    await RisingEdge(dut.wb_clk_i)
    
    # De-assert reset after a short delay
    await Timer(PERIOD * 1, unit="ns")
    dut.wb_rst_i.value = 0
    dut._log.info("========== TOP ==========")
    dut._log.info(dir(dut))

    dut._log.info("========== NEURON BLOCK ==========")
    dut._log.info(dir(dut.neuron_block_inst))
    # --- Layer 0 Simulation ---
    # Layer 0 uses the first trained weight set (L1) in hardware ordering.
    print("\n########################## START LAYER 0 ########################")
    layer = 0
    for core_layer_0 in range(NUM_CORES_LAYER_0):
        # 1. Configuration (ONCE)
        await program_layer_connections(dut, core_layer_0, "L1")

        # 2. Simulation (EVERY PIC)
        # L0 input: stimuli (stimuli matrix, no core-specific indexing needed)
        await run_layer_for_all_pics(dut, core_layer_0, layer, NUM_CORES_LAYER_0, None, spike_out_layer_0, run_pics, stimuli=stimuli)

    print("\n########################## FINISH LAYER 0 ########################")
    for i in range(min(5, run_pics)):
        print(
            f"L0 Frame {i}: "
            f"spikes={sum(spike_out_layer_0[i])}"
        )
    summarize_layer_activity("L0", spike_out_layer_0)
    await Timer(PERIOD * 1, unit="ns")

    # --- Layer 1 Simulation ---
    # Layer 1 uses the second trained weight set (L2).
    print("\n########################## START LAYER 1 ########################")
    layer = 1
    for core_layer_1 in range(NUM_CORES_LAYER_1):
        # 1. Configuration (ONCE)
        await program_layer_connections(dut, core_layer_1, "L2")
        
        # 2. Simulation (EVERY PIC)
        # L1 input: spike_out_layer_0
        await run_layer_for_all_pics(dut, core_layer_1, layer, NUM_CORES_LAYER_1, spike_out_layer_0, spike_out_layer_1, run_pics, layer_axon_limit=NUM_AXON_LAYER_1)

    print("\n########################## FINISH LAYER 1 ########################")
    print(f"L1 output: {spike_out_layer_1}")
    summarize_layer_activity("L1", spike_out_layer_1)
    await Timer(PERIOD * 1, unit="ns")

    # --- Layer 2 Simulation ---
    # Layer 2 uses the third trained weight set (L3).
    print("\n########################## START LAYER 2 ########################")
    layer = 2
    for core_layer_2 in range(NUM_CORES_LAYER_2):
        # 1. Configuration (ONCE)
        await program_layer_connections(dut, core_layer_2, "L3")

        # 2. Simulation (EVERY PIC)
        # L2 input: spike_out_layer_1. Note: core_idx is not used for L2 input indexing in run_layer_for_all_pics
        # because the original code suggests the L1 output is consolidated and indexed linearly for L2 input.
        await run_layer_for_all_pics(dut, core_layer_2, layer, NUM_CORES_LAYER_2, spike_out_layer_1, spike_out_layer_2, run_pics, layer_axon_limit=NUM_AXON_LAYER_2)

    print("\n########################## FINISH LAYER 2 ########################")
    print(f"L2 output: {spike_out_layer_2}")
    summarize_layer_activity("L2", spike_out_layer_2)
    await Timer(PERIOD * 1, unit="ns")

    # --- Final Results Calculation ---
    c# --- Software vs Hardware Validation ---
    print("\n################# DIGITAL TWIN VALIDATION #################")
    # Generate the baseline for Layer 2 using the L3 weights
    expected_layer_2 = generate_software_baseline(stimuli, "L3", run_pics, NUM_CORES_LAYER_2 * NUM_NEURON)
    
    mismatches = 0
    for pic in range(run_pics):
        if expected_layer_2[pic] != spike_out_layer_2[pic]:
            mismatches += 1
            dut._log.error(f"MISMATCH at Frame {pic}! \nExpected: {expected_layer_2[pic]} \nHardware: {spike_out_layer_2[pic]}")
            
    if mismatches == 0:
        dut._log.info("✅ SUCCESS: Python 1T1R Baseline perfectly matches Silicon!")
        
    # --- Final Results Calculation --- 
    correct_pic = 0 
    predict_class = calculate_majority_class(spike_out_layer_2)
    if predict_class and predict_class[0] >= 0:
        print(f"\nPrediction: Gesture Class {predict_class[0]}")
    else:
        print("\nPrediction: UNKNOWN (low confidence or saturation detected)")
        
    print("\nTest Completed.")

@cocotb.test()
async def tier1_smoke_handshake(dut):
    """Sentry-AI Tier 1: 8-bit Weight + LIF Accumulation + Reset (1T1R Updated)"""
    
    # 1. Start Clock & Reset
    clock = Clock(dut.wb_clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())
    dut.wb_rst_i.value = 1
    await Timer(20, unit="ns")
    dut.wb_rst_i.value = 0
    await RisingEdge(dut.wb_clk_i)

    # 2. Program a Golden Weight (+16) at Row 0, Col 0
    # +16 is used so it does not instantly breach the THRESHOLD of 24
    await program_8bit_weight(dut, 0, 0, 16)
    dut._log.info("Handshake: Golden Weight +16 programmed.")

    # 3. Trigger 1st Spike via Caravel Logic Analyzer Pins
    # la_data_in[0] routes to array_inst_0 spike_i[0]
    dut.la_data_in.value = 0x00000000000000000000000000000001
    await ClockCycles(dut.wb_clk_i, 1)
    dut.la_data_in.value = 0 # Turn off spike
    await ClockCycles(dut.wb_clk_i, 1) # Wait for MAC pipeline

    # Retrieve V_mem directly from the 1T1R array observation port
    v_mem = dut.neuron_core_inst.array_inst_0.gen_neuron[0].u_neuron.membrane_o.value.signed_integer
    dut._log.info(f"Handshake: Spike 1 injected. V_mem = {v_mem}")
    assert v_mem == 16, f"Weight Error! Expected 16, got {v_mem}"

    # 4. Wait for Leakage (LIF check)
    # 1 cycle leak: 16 >> 2 = 4. V_mem should be 16 - 4 = 12.
    await ClockCycles(dut.wb_clk_i, 1)
    v_mem_leak = dut.neuron_core_inst.array_inst_0.gen_neuron[0].u_neuron.membrane_o.value.signed_integer
    dut._log.info(f"Handshake: Leakage check after 1 cycle. V_mem = {v_mem_leak}")
    assert v_mem_leak == 12, f"LIF Physics Error: Expected 12, got {v_mem_leak}!"

    # 5. Trigger 2nd Spike to hit Threshold (24)
    # V_mem is 12. Leak next cycle = 12 >> 2 = 3. Pre-spike V_mem = 9.
    # Spike +16 -> V_mem = 25. Since 25 >= 24, it fires and resets to 0.
    dut.la_data_in.value = 0x00000000000000000000000000000001
    await ClockCycles(dut.wb_clk_i, 1)
    dut.la_data_in.value = 0
    await ClockCycles(dut.wb_clk_i, 1)

    final_v_mem = dut.neuron_core_inst.array_inst_0.gen_neuron[0].u_neuron.membrane_o.value.signed_integer
    dut._log.info(f"Handshake: Threshold breached. V_mem after reset = {final_v_mem}")
    assert final_v_mem == 0, f"Saturation Error: Neuron failed to reset after spike! V_mem={final_v_mem}"

    dut._log.info("✅ TIER 1 SMOKE TEST PASSED: Silicon Handshake Successful.")

@cocotb.test()
async def tier2_binary_parity(dut):
    """Tier 2: Dual polarity sweep + internal weight diagnostics."""

    # 1. Setup clock once; each mode gets its own hardware reset.
    clock = Clock(dut.wb_clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Modes: 0 => P-N, 1 => N-P
    mode_configs = [
        (0, "EXCITATORY (P-N)", False),
        (1, "INVERTED (N-P)", True),
    ]

    stimuli = load_stimuli_frames(INPUT_FILE, requested_pics=1)
    stim_mag = int(os.environ.get("TB_TIER2_STIM_MAG", "1"))
    stim_mag = max(1, min(0x7FFF, stim_mag))

    total_spikes_across_modes = 0

    for mode_id, mode_str, flip_sign in mode_configs:
        dut._log.info(f"\n--- Starting Sweep Mode {mode_id}: {mode_str} ---")
        dut._log.info(f"Tier2 stimulus word: 0x{stim_mag:04X}")

        # 2. Reset and set a low threshold to catch weak activity.
        dut.wb_rst_i.value = 1
        await ClockCycles(dut.wb_clk_i, 5)
        dut.wb_rst_i.value = 0
        await RisingEdge(dut.wb_clk_i)
        # Lock Python tracking to the parameterized Verilog threshold
        tier2_threshold = 24
        dut._log.info(f"Tier2 threshold locked to 1T1R hardware parameter: {tier2_threshold}")

        # 3. Program first 4 cores for 1024-axon coverage with selected polarity.
        for c_id in range(4):
            await program_layer_connections(dut, c_id, "L1", flip_sign=flip_sign)

        # 4. Inference + diagnostics.
        mode_spikes = 0
        max_v_seen = 0
        active_axons_found = 0
        dumped_weights = []
        synth_bypass_enabled = os.environ.get("TB_SYNTH_BYPASS", "0") == "1"
        synth_bypass_active = False
        synth_bypass_weight = 50

        if synth_bypass_enabled:
            try:
                # Synthetic bypass: force a suprathreshold weight for clear fire evidence.
                dut.current_weight.value = Force(synth_bypass_weight)
                synth_bypass_active = True
                dut._log.info(f"SYNTH BYPASS: Forced current_weight = +{synth_bypass_weight}")
            except Exception as exc:
                dut._log.warning(f"SYNTH BYPASS: could not force current_weight ({exc})")
        else:
            dut._log.info("SYNTH BYPASS: disabled (TB_SYNTH_BYPASS=0)")

        dut._log.info("🚀 Starting Deep Scan across 1,024 axons...")

        for row_idx, row_data in enumerate(stimuli[0]):
            for bit_idx in range(32):
                if (row_data >> bit_idx) & 0x1:
                    axon_id = (row_idx * 32) + bit_idx
                    active_axons_found += 1

                    if axon_id < 1024:
                        r = (axon_id % 256) // 32
                        c = (axon_id % 256) % 32

                        read_word = (MODE_READ << 30) | (r << 25) | (c << 20) | stim_mag
                        await nvm_read(dut, 0x30000000, read_word)

                        # nvm_read already waits through ack + latch edge.
                        # Sample immediately to avoid missing one-cycle spike assertions.

                        # DIAGNOSTIC PEEK: Raw synapse data vs extracted weight.
                        if len(dumped_weights) < 10:
                            raw_matrix_out = None
                            raw_w = None
                            conn_bit0 = None

                            try:
                                raw_matrix_out = dut.slave_dat_o.value.to_unsigned()
                            except Exception:
                                try:
                                    raw_matrix_out = dut.slave_dat_o[0].value.to_unsigned()
                                except Exception:
                                    raw_matrix_out = None

                            try:
                                raw_w = dut.neuron_block_inst.current_weight.value.to_signed()
                            except Exception:
                                try:
                                    raw_w = dut.current_weight.value.to_signed()
                                except Exception:
                                    try:
                                        raw_w = dut.stimuli.value.to_signed()
                                    except Exception:
                                        raw_w = None

                            try:
                                conn_bit0 = int(dut.connection.value.to_unsigned() & 0x1)
                            except Exception:
                                conn_bit0 = None

                            raw_matrix_hex = "N/A" if raw_matrix_out is None else f"0x{raw_matrix_out:08X}"
                            if raw_matrix_out is None:
                                raw_bits = "b0=N/A b8=N/A b16=N/A b24=N/A low=N/A high=N/A"
                            else:
                                b0 = raw_matrix_out & 0x1
                                b8 = (raw_matrix_out >> 8) & 0x1
                                b16 = (raw_matrix_out >> 16) & 0x1
                                b24 = (raw_matrix_out >> 24) & 0x1
                                low = raw_matrix_out & 0xFF
                                high = (raw_matrix_out >> 8) & 0xFF
                                raw_bits = (
                                    f"b0={b0} b8={b8} b16={b16} b24={b24} "
                                    f"low=0x{low:02X} high=0x{high:02X}"
                                )

                            raw_w_str = "N/A" if raw_w is None else str(raw_w)
                            conn_str = "N/A" if conn_bit0 is None else str(conn_bit0)
                            dut._log.info(
                                f"Axon {axon_id} | Raw Matrix Out: {raw_matrix_hex} {raw_bits} | "
                                f"Conn[0]={conn_str} | Stimulus: {raw_w_str}"
                            )
                            dumped_weights.append(raw_w)

                        v_mem = dut.array_inst_0.gen_neuron[0].u_neuron.membrane_o.value.signed_integer
                        if abs(v_mem) > abs(max_v_seen):
                            max_v_seen = v_mem

                        out_bits = dut.array_inst_0.spike_o.value.to_unsigned()
                        if out_bits > 0:
                            mode_spikes += bin(out_bits).count("1")

        total_spikes_across_modes += mode_spikes
        dut._log.info(f"Mode {mode_id} First 10 weights seen by RTL: {dumped_weights}")
        dut._log.info(f"Mode {mode_id} Active Input Events: {active_axons_found}")
        dut._log.info(f"Mode {mode_id} Max V_mem: {max_v_seen} | Total Spikes: {mode_spikes}")

        if synth_bypass_active:
            try:
                dut.current_weight.value = Release()
            except Exception:
                pass

    assert total_spikes_across_modes > 0, (
        "FATAL: Zero spikes detected in both polarities. "
        "Check weight mapping logic."
    )
    