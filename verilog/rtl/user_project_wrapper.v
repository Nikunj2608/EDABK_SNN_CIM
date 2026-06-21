`default_nettype none
module user_project_wrapper #(
    parameter BITS = 32
) (
`ifdef USE_POWER_PINS
    inout vdda1, inout vdda2,
    inout vssa1, inout vssa2,
    inout vccd1, inout vccd2,
    inout vssd1, inout vssd2,
`endif

    // Wishbone
    input         wb_clk_i,
    input         wb_rst_i,
    input         wbs_stb_i,
    input         wbs_cyc_i,
    input         wbs_we_i,
    input  [3:0]  wbs_sel_i,
    input  [31:0] wbs_dat_i,
    input  [31:0] wbs_adr_i,
    output        wbs_ack_o,
    output [31:0] wbs_dat_o,

    // Logic Analyzer
    input  [127:0] la_data_in,
    output [127:0] la_data_out,
    input  [127:0] la_oenb,

    // Digital IOs
    input  [38-1:0] io_in,   //  MPRJ_IO_PADS
    output [38-1:0] io_out,
    output [38-1:0] io_oeb,

    // Analog IOs (analog_io[k] <-> GPIO pad k+7)
    // Left floating/unused as 1T1R is a fully digital macro
    inout  [38-10:0] analog_io,

    // Extra user clock
    input   user_clock2,

    // IRQs
    output [2:0] user_irq
);
  parameter [31:0] ADDR_MATCH    = 32'h3000_000C; 

  wire [31:0] slave_dat [3:0]; // 4 IPs
  wire  [3:0] slave_ack;
  wire        slave_stb;
  wire        slave_cyc;
  wire        slave_we;
  wire [31:0] mem [3:0]; // 4 IPs

  nvm_neuron_core_64x64 neuron_core_inst (
    // MASTER
    .wb_clk_i (wb_clk_i),
    .wb_rst_i (wb_rst_i),
    .wbs_stb_i(wbs_stb_i),
    .wbs_cyc_i(wbs_cyc_i),
    .wbs_we_i (wbs_we_i),
    .wbs_sel_i(wbs_sel_i),
    .wbs_dat_i(wbs_dat_i),
    .wbs_adr_i(wbs_adr_i),
    .wbs_dat_o(wbs_dat_o),
    .wbs_ack_o(wbs_ack_o),

    // SLAVEs
    .slave_0_dat_i(slave_dat[0]),
    .slave_1_dat_i(slave_dat[1]),
    .slave_2_dat_i(slave_dat[2]),
    .slave_3_dat_i(slave_dat[3]),
    .slave_ack_i  (slave_ack),
    .slave_stb_o  (slave_stb),
    .slave_cyc_o  (slave_cyc),
    .slave_we_o   (slave_we),
    .slave_0_dat_o(mem[0]),
    .slave_1_dat_o(mem[1]),
    .slave_2_dat_o(mem[2]),
    .slave_3_dat_o(mem[3])
  );

  // ------------------------------------------------------------
  // Wishbone ACK Generator & Dummy Read Data
  // ------------------------------------------------------------
  reg [3:0] slave_ack_reg;
  always @(posedge wb_clk_i or posedge wb_rst_i) begin
      if (wb_rst_i) begin
          slave_ack_reg <= 4'b0;
      end else begin
          // Generate a 1-cycle delay ACK for Wishbone writes
          slave_ack_reg[0] <= slave_stb & slave_cyc & ~slave_ack_reg[0];
          slave_ack_reg[1] <= slave_stb & slave_cyc & ~slave_ack_reg[1];
          slave_ack_reg[2] <= slave_stb & slave_cyc & ~slave_ack_reg[2];
          slave_ack_reg[3] <= slave_stb & slave_cyc & ~slave_ack_reg[3];
      end
  end
  assign slave_ack = slave_ack_reg;
  
  assign slave_dat[0] = 32'b0; // Default dummy read data
  assign slave_dat[1] = 32'b0;
  assign slave_dat[2] = 32'b0;
  assign slave_dat[3] = 32'b0;

  // ------------------------------------------------------------
  // SNN Spiking Interconnect (Mapped to Caravel LA Pins)
  // ------------------------------------------------------------
  wire [31:0] spike_in_0  = la_data_in[31:0];
  wire [31:0] spike_in_1  = la_data_in[63:32];
  wire [31:0] spike_in_2  = la_data_in[95:64];
  wire [31:0] spike_in_3  = la_data_in[127:96];

  wire [15:0] spike_out_0, spike_out_1, spike_out_2, spike_out_3;
  assign la_data_out[15:0]   = spike_out_0;
  assign la_data_out[31:16]  = spike_out_1;
  assign la_data_out[47:32]  = spike_out_2;
  assign la_data_out[63:48]  = spike_out_3;
  assign la_data_out[127:64] = 64'b0; // Unused LA pins

  // ------------------------------------------------------------
  // Instance 0 
  // ------------------------------------------------------------
  wire       cfg_we_0   = slave_stb & slave_cyc & slave_we & (mem[0][31:30] == 2'b11);
  wire [4:0] row_0      = mem[0][29:25];
  wire [3:0] neuron_0   = mem[0][23:20]; 
  wire       sign_0     = mem[0][7];  
  wire [2:0] level_0    = mem[0][2:0];

  reram_1t1r_snn_array_32x32 #(
      .ROWS(32),
      .N_NEURONS(16),
      .G_BITS(3),
      .MEM_BITS(16)
  ) array_inst_0 (
      .clk_i       (wb_clk_i),
      .rst_ni      (~wb_rst_i),
      .en_i        (1'b1),
      .spike_i     (spike_in_0), 
      .cfg_we_i    (cfg_we_0),
      .cfg_neuron_i(neuron_0),
      .cfg_sign_i  (sign_0),
      .cfg_row_i   (row_0),
      .cfg_level_i (level_0),
      .spike_o     (spike_out_0),
      .membrane_o  (), // Unconnected observation port
      .syn_sum_o   ()  // Unconnected observation port
  );

  // ------------------------------------------------------------
  // Instance 1
  // ------------------------------------------------------------
  wire       cfg_we_1   = slave_stb & slave_cyc & slave_we & (mem[1][31:30] == 2'b11);
  wire [4:0] row_1      = mem[1][29:25];
  wire [3:0] neuron_1   = mem[1][23:20]; 
  wire       sign_1     = mem[1][7];  
  wire [2:0] level_1    = mem[1][2:0];

  reram_1t1r_snn_array_32x32 #(
      .ROWS(32),
      .N_NEURONS(16),
      .G_BITS(3),
      .MEM_BITS(16)
  ) array_inst_1 (
      .clk_i       (wb_clk_i),
      .rst_ni      (~wb_rst_i),
      .en_i        (1'b1),
      .spike_i     (spike_in_1), 
      .cfg_we_i    (cfg_we_1),
      .cfg_neuron_i(neuron_1),
      .cfg_sign_i  (sign_1),
      .cfg_row_i   (row_1),
      .cfg_level_i (level_1),
      .spike_o     (spike_out_1),
      .membrane_o  (),
      .syn_sum_o   ()
  );

  // ------------------------------------------------------------
  // Instance 2
  // ------------------------------------------------------------
  wire       cfg_we_2   = slave_stb & slave_cyc & slave_we & (mem[2][31:30] == 2'b11);
  wire [4:0] row_2      = mem[2][29:25];
  wire [3:0] neuron_2   = mem[2][23:20]; 
  wire       sign_2     = mem[2][7];  
  wire [2:0] level_2    = mem[2][2:0];

  reram_1t1r_snn_array_32x32 #(
      .ROWS(32),
      .N_NEURONS(16),
      .G_BITS(3),
      .MEM_BITS(16)
  ) array_inst_2 (
      .clk_i       (wb_clk_i),
      .rst_ni      (~wb_rst_i),
      .en_i        (1'b1),
      .spike_i     (spike_in_2), 
      .cfg_we_i    (cfg_we_2),
      .cfg_neuron_i(neuron_2),
      .cfg_sign_i  (sign_2),
      .cfg_row_i   (row_2),
      .cfg_level_i (level_2),
      .spike_o     (spike_out_2),
      .membrane_o  (),
      .syn_sum_o   ()
  );

  // ------------------------------------------------------------
  // Instance 3
  // ------------------------------------------------------------
  wire       cfg_we_3   = slave_stb & slave_cyc & slave_we & (mem[3][31:30] == 2'b11);
  wire [4:0] row_3      = mem[3][29:25];
  wire [3:0] neuron_3   = mem[3][23:20]; 
  wire       sign_3     = mem[3][7];  
  wire [2:0] level_3    = mem[3][2:0];

  reram_1t1r_snn_array_32x32 #(
      .ROWS(32),
      .N_NEURONS(16),
      .G_BITS(3),
      .MEM_BITS(16)
  ) array_inst_3 (
      .clk_i       (wb_clk_i),
      .rst_ni      (~wb_rst_i),
      .en_i        (1'b1),
      .spike_i     (spike_in_3), 
      .cfg_we_i    (cfg_we_3),
      .cfg_neuron_i(neuron_3),
      .cfg_sign_i  (sign_3),
      .cfg_row_i   (row_3),
      .cfg_level_i (level_3),
      .spike_o     (spike_out_3),
      .membrane_o  (),
      .syn_sum_o   ()
  );

endmodule
