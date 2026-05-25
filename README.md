<table>
  <tr>
    <td align="center"><img src="img/bm-lab-logo-white.jpg" alt="BM LABS Logo" width="200"/></td>
    <td align="center"><img src="img/chip_foundry_logo.png" alt="Chipfoundry Logo" width="200"/></td>
    <td align="center"><img src="img/EDA_logo_Darkblue.png" alt="EDABK Logo" width="110"/></td>
  </tr>
</table>

# EDABK_SNN_CIM

> This project, submitted to **The NVM Innovation Contest**, introduces a Neurosynaptic Core for hand gesture recognition. The design is based on a hybrid Artificial and Spiking Neural Network architecture and integrates the ReRAM-based NVM IP from BM Labs with the ChipFoundry Caravel SoC Platform.

## Contributors

All members are affiliated to EDABK Laboratory, School of Electrical and Electronic Engineering, Hanoi University of Science and Technology (HUST).

| No. | Name                                                         | Study programme                           | Relevant link |
| --- | ------------------------------------------------------------ | ----------------------------------------- | ------------- |
| 1   | [Phuong-Linh Nguyen](mailto:linh.nguyenphuong1@sis.hust.edu.vn) | Master of Engineer in IC Design           |               |
| 2   | [Anh-Dung Hoang](mailto:dung.ha240324e@sis.hust.edu.vn)         | Master of Engineer in IC Design           |               |
| 3   | [Ngoc-Duong Nguyen](mailto:duong.nn242535m@sis.hust.edu.vn)     | Master of Science in IC Design            |               |
| 4   | [Hoang-Son Nguyen](mailto:son.nh210741@sis.hust.edu.vn)         | Bachelor in Electronics Engineering       |               |
| 5   | [Viet-Tung Pham](mailto:tung.pv224415@sis.hust.edu.vn)          | Senior student in Electronics Engineering |               |
| 6   | [Thanh-Hang Vu](mailto:hang.vt233385@sis.hust.edu.vn)           | Junior student in Electronics Engineering |               |

## Abstract

The application of hand gesture recognition can be extended to advanced human-machine interaction, enabling touchless control in various domains (e.g., automotive, healthcare). However, deploying such Artificial Intelligence (AI) models on edge devices is often hindered by the latency and power consumption arising from the von Neumann bottleneck, where data must be constantly shuttled between memory and processing units.

From an algorithmic standpoint, Spiking Neural Networks (SNNs) offer a promising solution. Inspired by how the biological brain communicates using discrete neural spikes, SNNs can reduce the quantity and complexity of computations. To compensate for the potential accuracy degradation in pure SNNs, a hybrid approach combining them with Artificial Neural Networks (ANNs) is employed. This allows high-precision input features to be processed, leading to significant accuracy improvements over traditional SNNs.

On the hardware side, implementing large models presents challenges, especially concerning the storage of trainable parameters (e.g., weights, synaptic connections) which would otherwise need to be reloaded into SRAM or flip-flops before each classification. The use of Non-Volatile ReRAM addresses this by preserving the parameters even when the embedded device enters a deep-sleep state. The current RTL simulation path uses the Neuromorphic X2 behavioral model, which adds READ, PROGRAM, and COMPUTE-mode support around the ReRAM-style 32x32 array.

Therefore, our team proposes **EDABK_SNN_CIM**, a solution integrating the ReRAM-based NVM IP from BM Labs and the ChipFoundry Caravel SoC Platform. The overall architecture is described in the [System Block Diagram](#system-block-diagram) section.

## System Block Diagram

![Neuron Core Diagram](img/README_block_diagram.png)
The proposed system accepts 13 features as input, corresponding to position, orientation, acceleration, and angular velocity, which are captured by Inertial Measurement Unit (IMU) sensors during human hand movements. Based on this data, the system predicts which gesture class the motion belongs to.

A hardware/software co-design approach is planned for the system implementation. The hardware component, responsible for the primary Neural Network computations, is a Caravel SoC integrated with BM Labs’ NVM IP. The software component, which can run on a host PC or an embedded device, is tasked with encoding sensor data, inferring the final gesture label, and controlling the hardware's operation.

Within the hardware's `user_project_wrapper`, a Controller utilizing a Wishbone Interface manages overall data exchange. The encoded sensor data is first pushed into a Stimuli-in Buffer before being processed by the ReRAM Crossbar array within the BM Labs’ NVM IP. An Address Decoder determines the specific IP commands, thereby selecting the appropriate rows and columns of the array to be accessed. The computational results are then stored in a Spike-out Buffer before being returned to the software component.

## Timeline

- Week 1 (October 13-19):

  + Research and select an optimal Neural Network model for gesture recognition.
  + Architectural design the Neural Accelerator.
- Week 2 (October 20-26):

  + Develop RTL code and perform functional verification for the modules within the Neural Accelerator.
  + Integrate the custom modules with the provided IP and the Caravel Template.
- Week 3 (October 27 - November 2):

  + Conduct system-level simulation and verification, including timing constraints.
  + Resolve any DRC and LVS violations that arise from the tool flow.

## Role of the ReRAM IP in In-Memory Computing (IMC)

The Neuromorphic X2 ReRAM behavioral model from BM Labs is used in this project not only as a storage element, but as the **core hardware model that enables In-Memory Computing (IMC)** during RTL verification. Each cell in the ReRAM crossbar stores a binary synaptic state.

The digital RTL we designed:

- Sends READ, PROGRAM, and X2 COMPUTE-mode commands to the ReRAM IP model (`nvm_synapse_matrix.v`),
- Receives the resulting binary synapse outputs (i.e., whether current exceeds a threshold),
- Passes these into the digital neuron array (`nvm_neuron_block.v`), where final accumulation and spike generation occur.

## RTL Implementation Overview

The digital hardware of the system is implemented entirely inside the [`SNN_gesture/`](https://github.com/<username>/EDABK_SNN_CIM/tree/main/verilog/rtl/SNN_gesture) directory.
The design follows a modular structure and is fully synthesizable on the Caravel SoC.

| Module                       | Function                                                                                                                                                          |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nvm_core_decoder.v`       | Decodes address ranges (`wbs_adr_i[15:12]`) and routes Wishbone signals to either Synapse Matrix, Spike Memory, or Picture-Done handler.                        |
| `nvm_synapse_matrix.v`     | Instantiates Neuromorphic_X2 behavioral ReRAM macros. Broadcasts commands (PROGRAM/READ/COMPUTE) and concatenates 1-bit read outputs into a synapse vector. |
| `nvm_neuron_block.v`       | Digital LIF neuron array. Performs spatial accumulation during `enable`, then evaluates threshold, spike generation, membrane reset, and leak on `picture_done`. |
| `nvm_neuron_spike_out.v`   | Stores 64 output spikes into 4×16-bit registers. Accessible via Wishbone at address `0x3000_1000`.                                                             |
| `nvm_neuron_core_256x64.v` | Top-level module combining all blocks, interfaces to Wishbone bus, controls data flow between software, ReRAM synapses, neurons, and spike output memory.         |

## System Architecture and Recent Upgrades

The application of hand gesture recognition can be extended to advanced human-machine interaction, enabling touchless control in various domains. However, deploying AI models on edge devices is often hindered by the von Neumann bottleneck.

This architecture addresses that challenge by integrating **In-Memory Computing (IMC)** using non-volatile ReRAM macros to store synaptic weights directly at the compute nodes.

### Recent Architectural Upgrades

1. **True Leaky Integrate-and-Fire (LIF) Dynamics:**
   The digital neuron block (`nvm_neuron_block.v`) has been upgraded from a static accumulator to a full LIF model. It separates **spatial accumulation** (Wishbone data streaming) from **temporal evaluation** (leaking and firing at the frame boundary) to correctly process asynchronous temporal data.

2. **DVS128 Gesture Integration:**
   The end-to-end verification pipeline now supports asynchronous event-camera traffic (IBM DVS128 Dataset) via dynamic Python parsers (`dvs_parser.py`) in the testbench.

3. **ReRAM Conductance Degradation Modeling:**
   The digital verification flow integrates Python-based analog ReRAM physics models to emulate hardware aging and LRS/HRS drift over time.

4. **Neuromorphic X2 Behavioral Model Integration:**
   The main RTL and testbench integration now use `Neuromorphic_X2_wb` instead of the older X1 behavioral model. The tracked files are `verilog/rtl/neuron_core/hdl/Neuromorphic_X2_Beh.v` for simulation and `verilog/rtl/neuron_core/hdl/NEUROMORPHIC_X2_stub.v` for OpenLane elaboration.

## RTL Operation (LIF Dynamics)

The RTL runs in a continuous spatial-temporal loop over the Wishbone bus:

### 1. In-Memory Synapse Access

- `nvm_synapse_matrix.v` performs in-memory synaptic multiplication.
- In READ mode, each ReRAM column returns a 1-bit output, forming the neuron `connection` mask.
- In X2 COMPUTE mode, the model can consume a 32-entry input vector and push 16-bit dot-product results into its output FIFO.

### 2. Spatial Accumulation

- During the `enable` strobe, the neuron block accumulates signed stimuli across the 256 axons serially.

### 3. Temporal Tick and Fire

- When `picture_done` is asserted (end of one temporal frame), each neuron evaluates its membrane potential, fires if threshold is reached, and otherwise applies leak.

```verilog
// TEMPORAL TICK: Evaluate, Fire, and Leak
if (picture_done) begin
    if (potential[i] >= THRESHOLD) begin
        spike_o[i]   <= 1'b1;   // Fire spike
        potential[i] <= 16'b0;  // Reset membrane
    end else begin
        spike_o[i]   <= 1'b0;
        // Apply temporal leak
        if (potential[i] > LEAK)
            potential[i] <= potential[i] - LEAK;
        else
            potential[i] <= 16'b0;
    end
end
```

### 4. Spike Output and Readback

After each frame, the spike vector is stored in `nvm_neuron_spike_out.v` and read through Wishbone:

| Wishbone Address | Data Returned             |
| ---------------- | ------------------------- |
| `0x3000_1000`    | Spikes for neurons 0-15   |
| `0x3000_1002`    | Spikes for neurons 16-31  |
| `0x3000_1004`    | Spikes for neurons 32-47  |
| `0x3000_1006`    | Spikes for neurons 48-63  |

## ReRAM SNN 1T1R Additions

A new **ReRAM-based SNN flow using 1T1R neuron/synapse abstractions** has been added as an optional path for development and verification. This addition is intended for users who want to evaluate a generic ReRAM SNN implementation alongside the original digital flow, without changing the existing baseline RTL structure.

### What was added

The following new files were added:

```text
analog_snn/
├── README.md
├── reram_snn_32x32.py
├── reram_snn_32x32_1t1r.py
└── demo_reram_snn_32x32_1t1r.py

verilog/rtl/neuron_core/hdl/
├── reram_1t1r_snn_neuron.v
└── reram_1t1r_snn_array_32x32.v

verilog/dv/cocotb/reram_1t1r/
├── README.md
├── Makefile
└── test_reram_1t1r.py
```

### Purpose of the new ReRAM SNN files

- `analog_snn/reram_snn_32x32.py`  
  Base behavioral ReRAM crossbar model.

- `analog_snn/reram_snn_32x32_1t1r.py`  
  1T1R ReRAM SNN behavioral model for 32×32 array-style experiments.

- `analog_snn/demo_reram_snn_32x32_1t1r.py`  
  Minimal runnable demo showing how to instantiate and execute the Python model.

- `verilog/rtl/neuron_core/hdl/reram_1t1r_snn_neuron.v`  
  Behavioral RTL abstraction of a ReRAM 1T1R spiking neuron.

- `verilog/rtl/neuron_core/hdl/reram_1t1r_snn_array_32x32.v`  
  Behavioral RTL abstraction of a 32×32 ReRAM 1T1R SNN array.

- `verilog/dv/cocotb/reram_1t1r/test_reram_1t1r.py`  
  Cocotb-based verification for the added ReRAM 1T1R SNN RTL.

### How to use the Python ReRAM SNN model

From the repository root:

```bash
cd analog_snn
python demo_reram_snn_32x32_1t1r.py
```

This runs the behavioral 1T1R ReRAM SNN example and prints the resulting output activity.

### How to use the Cocotb verification

From the repository root:

```bash
cd verilog/dv/cocotb/reram_1t1r
make
```

This launches the cocotb-based verification flow for the newly added ReRAM 1T1R SNN RTL files.

## Running the Cocotb Verification Environment

To test system-level SNN routing and LIF physics, a complete cocotb simulation environment is provided.

For Ubuntu/Linux users, running in an isolated Python virtual environment is recommended to avoid `cocotb-config` path issues.

### Step 1: Clone the repository

```bash
git clone https://github.com/<your-username>/EDABK_SNN_CIM.git
cd EDABK_SNN_CIM
```

### Step 2: Set up a virtual environment

```bash
cd verilog/tb
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install cocotb aedat numpy
```

### Step 4: Run the simulation

```bash
make
```

The simulation dynamically generates Wishbone transactions, streams stimuli through the ReRAM matrix, evaluates LIF neuron potentials, and outputs final gesture classification spikes.

### Integration note

The 1T1R additions are **optional** and are meant to extend the repository with a ReRAM-based SNN path. The main wrapper path has separately been updated to use the Neuromorphic X2 behavioral model.


## Replicating Locally

### Follow these steps to set up your environment and harden the design:

1. **Clone the Repository:**

```bash
git clone https://github.com/schizoneko/EDABK_SNN_CIM.git
```

2. **Prepare Your Environment:**

```bash
cd EDABK_SNN_CIM
make setup
```

3. **Install IPM:**

```bash
pip install cf-ipm
```

4. **Use the tracked Neuromorphic X2 model:**

The X2 behavioral model and OpenLane stub are now checked into the RTL tree:

```text
verilog/rtl/neuron_core/hdl/Neuromorphic_X2_Beh.v
verilog/rtl/neuron_core/hdl/NEUROMORPHIC_X2_stub.v
```

No manual module rename is required. The RTL include file points to `Neuromorphic_X2_Beh.v`, and the OpenLane wrapper config points to `NEUROMORPHIC_X2_stub.v`.

5. **Harden the Neuron Core:**

```bash
make neuron_core
```
6. **Harden the Design:**

```bash
make SNN_gesture
```

### Physical macro note

The repository now has the X2 behavioral model and X2 Verilog stub. Before final PnR/signoff, confirm that matching X2 physical views are available (`.lef`, `.gds`, `.lib`) or that the project intentionally maps the X2 stub to the existing physical macro collateral.

## Documentation

- Neuromorphic X2 behavioral model: `verilog/rtl/neuron_core/hdl/Neuromorphic_X2_Beh.v`
- Neuromorphic X2 OpenLane stub: `verilog/rtl/neuron_core/hdl/NEUROMORPHIC_X2_stub.v`
- Original Neuromorphic X1 IP reference: [Neuromorphic X1 documentation](https://github.com/BMsemi/Neuromorphic_X1_32x32)
- Competition details: [ChipFoundry BM Labs Challenge](https://chipfoundry.io/challenges/bmlabs)

## License

This project is licensed under Apache 2.0 - see LICENSE file for details.
