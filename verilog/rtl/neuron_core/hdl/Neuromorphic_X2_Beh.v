`timescale 1ns / 1ps

// *** NEUROMORPHIC_X2 Behavioral Model Code ***

// -----------------------------------------------------------------------------
// Wishbone shim: expose ONE address (0x3000_000C).
//  - WB WRITE @ 0x3000_000C  -> send command into core
//  - WB READ  @ 0x3000_000C  -> get result from core
// -----------------------------------------------------------------------------

`ifdef USE_POWER_PINS
    `define USE_PG_PIN
`endif

module Neuromorphic_X2_wb (
    `ifdef USE_PG_PIN
      input VDDC,
      input VDDA,
      input VSS,
    `endif
    input         user_clk,     // user clock
    input         user_rst,     // user reset
    input         wb_clk_i,     // Wishbone clock
    input         wb_rst_i,     // Wishbone reset (Active High)
    input         wbs_stb_i,    // Wishbone strobe
    input         wbs_cyc_i,    // Wishbone cycle indicator
    input         wbs_we_i,     // Wishbone write enable: 1=write, 0=read
    input  [3:0]  wbs_sel_i,    // Wishbone byte select (must be 4'hF for 32-bit op)
    input  [31:0] wbs_dat_i,    // Wishbone write data (becomes DI to core)
    input  [31:0] wbs_adr_i,    // Wishbone address
    output [31:0] wbs_dat_o,    // Wishbone read data output (driven by DO from core)
    output        wbs_ack_o,     // Wishbone acknowledge output (ack_out from core)
  
    // Scan/Test Pins
    input         ScanInCC,        // Scan enable
    input         ScanInDL,        // Data scan chain input (user_clk domain)
    input         ScanInDR,        // Data scan chain input (wb_clk domain)
    input         TM,              // Test mode
    output        ScanOutCC,       // Data scan chain output

    // Analog Pins
    input         Iref,            // 100 µA current reference
    input         Vcc_read,        // 0.3 V read rail
    input         Vcomp,           // 0.6 V comparator bias
    input         Bias_comp2,      // 0.6 V comparator bias
    input         Vcc_wl_read,     // 0.7 V wordline read rail
    input         Vcc_wl_set,      // 1.8 V wordline set rail
    input         Vbias,           // 1.8 V analog bias
    input         Vcc_wl_reset,    // 2.6 V wordline reset rail
    input         Vcc_set,         // 3.3 V array set rail
    input         Vcc_reset,       // 3.3 V array reset rail
    input         Vcc_L,           // 5 V level shifter supply
    input         Vcc_Body         // 5 V body-bias supply
);

  parameter [31:0] ADDR_MATCH = 32'h3000_000C;
	parameter integer P = 0;
	
  // --------------------------------------------------------------------------
  // Internal wires connecting the shim to the behavioral core
  // --------------------------------------------------------------------------
  wire        CLKin;
  wire        RSTin;
  wire        EN;
  wire [31:0] DI;
  wire        W_RB;
  wire [31:0] DO;
  wire        ack_out;
	
  // Map WB to core
  assign EN = (wbs_stb_i && wbs_cyc_i && (wbs_adr_i == ADDR_MATCH) && (wbs_sel_i == 4'hF));
  assign CLKin      = wb_clk_i;
  assign RSTin      = wb_rst_i;
  assign DI         = wbs_dat_i;
  assign W_RB       = wbs_we_i;
  assign wbs_dat_o  = DO;
  assign wbs_ack_o  = ack_out;
	
  // Instantiate the behavioral core
  Neuromorphic_X2_beh #(.P(P))
	core_inst (
    `ifdef USE_PG_PIN
      .VDDC(VDDC),
      .VDDA(VDDA),
      .VSS(VSS),
    `endif
    .CLKin      (CLKin),
    .RSTin      (RSTin),
    .EN         (EN),
    .DI         (DI),
    .W_RB       (W_RB),
    .DO         (DO),
    .ack_out    (ack_out),
    
    // Scan/Test Pins
    .ScanInCC(ScanInCC),
    .ScanInDL(ScanInDL),
    .ScanInDR(ScanInDR),
    .TM(TM),
    .ScanOutCC(ScanOutCC),

    // Analog Pins
    .Iref(Iref),
    .Vcc_read(Vcc_read),
    .Vcomp(Vcomp),
    .Bias_comp2(Bias_comp2),
    .Vcc_wl_read(Vcc_wl_read),
    .Vcc_wl_set(Vcc_wl_set),
    .Vbias(Vbias),
    .Vcc_wl_reset(Vcc_wl_reset),
    .Vcc_set(Vcc_set),
    .Vcc_reset(Vcc_reset),
    .Vcc_L(Vcc_L),
    .Vcc_Body(Vcc_Body)
  );
	
endmodule


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

module Neuromorphic_X2_beh (
    `ifdef USE_PG_PIN
      input  wire VDDC,
      input  wire VDDA,
      input  wire VSS,
    `endif

    input  wire        CLKin,
    input  wire        RSTin,
    input  wire        EN,
    input  wire [31:0] DI,
    input  wire        W_RB,          // 1 = WRITE, 0 = READ
    output reg  [31:0] DO,
    output reg         ack_out,

    // Scan/Test Pins (unused in this behavioral model)
    input  wire        ScanInCC,      // Scan enable
    input  wire        ScanInDL,      // Data in (user_clk domain)
    input  wire        ScanInDR,      // Data in (wb_clk domain)
    input  wire        TM,            // Test mode
    output wire        ScanOutCC,     // Scan data out

    // Analog Pins (present for interface; unused in this behavioral model)
    input  wire        Iref,          // 100 µA current reference
    input  wire        Vcc_read,      // 0.3 V read rail
    input  wire        Vcomp,         // 0.6 V comparator bias
    input  wire        Bias_comp2,    // 0.6 V comparator bias
    input  wire        Vcc_wl_read,   // 0.7 V wordline read rail
    input  wire        Vcc_wl_set,    // 1.8 V wordline set rail
    input  wire        Vbias,         // 1.8 V analog bias
    input  wire        Vcc_wl_reset,  // 2.6 V wordline reset rail
    input  wire        Vcc_set,       // 3.3 V set rail
    input  wire        Vcc_reset,     // 3.3 V reset rail
    input  wire        Vcc_L,         // 5 V level shifter
    input  wire        Vcc_Body       // 5 V body-bias
);

  assign ScanOutCC = 1'b0;

  // ---------------------------------------------------------------------------
  // Parameters (simulation delays / constants)
  // ---------------------------------------------------------------------------
  parameter integer RD_Dly      = 44;          // cycles before read data is available
  parameter integer WR_Dly      = 200;         // cycles to simulate write latency
  parameter integer CMP_Dly     = 1;
  parameter [31:0] EMPTY_TOKEN  = 32'hDEAD_C0DE;
	
	parameter integer P = 1;

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------
  integer r, c, k, m, n, col, row, x, y, q;                          // loop indices for init and delays

  // 32x32 8-bit memory array (row = [29:25], col = [24:20])
  reg array_mem [0:31][0:31];  // 32x32 memory array (1-bit values)

  // Two 32-deep FIFOs (behavioral)
  reg [31:0] ip_fifo [0:31];                   // WB -> Engine commands
  reg [31:0] op_fifo [0:31];                   // Engine -> WB results

  // --- 5-bit pointers + separate wrap flags (preserves original semantics) ---
  // Input FIFO (WB producer / Engine consumer)
  reg  [4:0] ip_wptr_idx;   // producer index (WB)
  reg        ip_wptr_wrap;  // producer wrap bit
  reg  [4:0] ip_rptr_idx;   // consumer index (Engine)
  reg        ip_rptr_wrap;  // consumer wrap bit

  // Output FIFO (Engine producer / WB consumer)
  reg  [4:0] op_wptr_idx;   // producer index (Engine)
  reg        op_wptr_wrap;  // producer wrap bit
  reg  [4:0] op_rptr_idx;   // consumer index (WB)
  reg        op_rptr_wrap;  // consumer wrap bit

  // FIFO status using index + wrap flags
  wire ip_empty = (ip_wptr_idx == ip_rptr_idx) && (ip_wptr_wrap == ip_rptr_wrap);
  wire ip_full  = (ip_wptr_idx == ip_rptr_idx) && (ip_wptr_wrap != ip_rptr_wrap);

  wire op_empty = (op_wptr_idx == op_rptr_idx) && (op_wptr_wrap == op_rptr_wrap);
  wire op_full  = (op_wptr_idx == op_rptr_idx) && (op_wptr_wrap != op_rptr_wrap);
	
	// Next index helpers
  wire [4:0] ip_wptr_idx_next = (ip_wptr_idx == 5'd31) ? 5'd0 : (ip_wptr_idx + 5'd1);
  wire       ip_wptr_wrap_next = (ip_wptr_idx == 5'd31) ? ~ip_wptr_wrap : ip_wptr_wrap;

  wire [4:0] ip_rptr_idx_next = (ip_rptr_idx == 5'd31) ? 5'd0 : (ip_rptr_idx + 5'd1);
  wire       ip_rptr_wrap_next = (ip_rptr_idx == 5'd31) ? ~ip_rptr_wrap : ip_rptr_wrap;

  wire [4:0] op_wptr_idx_next = (op_wptr_idx == 5'd31) ? 5'd0 : (op_wptr_idx + 5'd1);
  wire       op_wptr_wrap_next = (op_wptr_idx == 5'd31) ? ~op_wptr_wrap : op_wptr_wrap;

  wire [4:0] op_rptr_idx_next = (op_rptr_idx == 5'd31) ? 5'd0 : (op_rptr_idx + 5'd1);
  wire       op_rptr_wrap_next = (op_rptr_idx == 5'd31) ? ~op_rptr_wrap : op_rptr_wrap;

  // Engine state
  reg        in_process;                        // engine busy flag
  reg [31:0] DI_local;                          // latched command
  reg [31:0] DO_local;                          // latched read data
	reg [15:0] temp_comp_data;

  // Compute FIFO to store the 8-bit LSB of the compute vector (1x32)
  reg [7:0] compute_fifo [0:31];               // FIFO to store 8-bit LSBs of input vector
  reg [4:0] compute_wptr_idx;                  // Write pointer for the compute FIFO
  reg [4:0] compute_rptr_idx;                  // Read pointer for the compute FIFO
  reg compute_wptr_wrap;                       // Wrap flag for write pointer
  reg compute_rptr_wrap;                       // Wrap flag for read pointer

  // FIFO helpers for Compute FIFO
  wire [4:0] compute_wptr_idx_next = (compute_wptr_idx == 5'd31) ? 5'd0 : (compute_wptr_idx + 5'd1);
  wire compute_wptr_wrap_next = (compute_wptr_idx == 5'd31) ? ~compute_wptr_wrap : compute_wptr_wrap;

  wire [4:0] compute_rptr_idx_next = (compute_rptr_idx == 5'd31) ? 5'd0 : (compute_rptr_idx + 5'd1);
  wire compute_rptr_wrap_next = (compute_rptr_idx == 5'd31) ? ~compute_rptr_wrap : compute_rptr_wrap;
	
	wire compute_fifo_full = (compute_wptr_idx == compute_rptr_idx) && (compute_wptr_wrap != compute_rptr_wrap);
  wire compute_fifo_empty = (compute_wptr_idx == compute_rptr_idx) && (compute_wptr_wrap == compute_rptr_wrap);
	
	reg [31:0] temp_data;  // Present just to see data (can be removed)
	reg [7:0] comp_memory [0:31];
	
	reg [7:0] temp_data1; // Present just to see data (can be removed)
	
	// Create local copies of input read pointers
  reg [4:0] temp_ip_rptr_idx;  // Used to increment rd_ptr in one clk for all 32 datas
  reg       temp_ip_rptr_wrap;  // Used to increment rd_ptr in one clk for all 32 datas
	
	// Create local copies of output read pointers
  reg [4:0] temp_op_rptr_idx;  // Used to increment rd_ptr in one clk for all 32 datas
  reg       temp_op_rptr_wrap;  // Used to increment rd_ptr in one clk for all 32 datas
	
	// Temp pointers for reading compute FIFO and writing to OP FIFO
  reg [4:0] temp_compute_rptr_idx;  // Used to increment rd_ptr in one clk for all 32 datas
  reg       temp_compute_rptr_wrap;  // Used to increment rd_ptr in one clk for all 32 datas
  reg [4:0] temp_op_wptr_idx;  // Used to increment rd_ptr in one clk for all 32 datas
  reg       temp_op_wptr_wrap;  // Used to increment rd_ptr in one clk for all 32 datas
	
	reg [4:0] local_compute_rptr_idx;  // Used to increment rd_ptr in one clk for all 32 datas inside compute (col) for loop
  reg       local_compute_rptr_wrap;  // Used to increment rd_ptr in one clk for all 32 datas inside compute (col) for loop

  // ---------------------------------------------------------------------------
  // Wishbone side (behavioral, decoupled from engine)
  // ---------------------------------------------------------------------------
  always @(posedge CLKin or posedge RSTin) begin
    if (RSTin) begin
		  $display("P = %d",P);
      DO          <= 32'd0;
      ack_out     <= 1'b0;
      ip_wptr_idx <= 5'd0;
      ip_wptr_wrap<= 1'b0;
      op_rptr_idx <= 5'd0;
      op_rptr_wrap<= 1'b0;
    end else begin
      ack_out <= 1'b0;
      // WRITE request -> push to ip_fifo if not full
      if (EN && W_RB && !ack_out) begin
        if (!ip_full) begin
          ack_out <= 1'b1;
          ip_fifo[ip_wptr_idx] <= DI;
          ip_wptr_idx  <= ip_wptr_idx_next;
          ip_wptr_wrap <= ip_wptr_wrap_next;
        end
      end
      // READ request -> pop from op_fifo or return token if empty
      else if (EN && !W_RB && !ack_out) begin
        if (!op_empty) begin
          ack_out <= 1'b1;
          DO      <= op_fifo[op_rptr_idx];
          op_rptr_idx  <= op_rptr_idx_next;
          op_rptr_wrap <= op_rptr_wrap_next;
        end else begin
          ack_out <= 1'b1;
          DO      <= EMPTY_TOKEN;
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // Engine side (simulation-only)
  // ---------------------------------------------------------------------------
  always @(posedge CLKin or posedge RSTin) begin
    if (RSTin) begin
      in_process   <= 1'b0;
      ip_rptr_idx  <= 5'd0;
      ip_rptr_wrap <= 1'b0;
      op_wptr_idx  <= 5'd0;
      op_wptr_wrap <= 1'b0;
			
			compute_wptr_idx  <= 5'd0;
			compute_rptr_idx  <= 5'd0;
			compute_wptr_wrap <= 1'b0;
			compute_rptr_wrap <= 1'b0;
			
    end else begin
      if (!in_process) begin
        if (!ip_empty) begin
          in_process <= 1'b1;
          DI_local   = ip_fifo[ip_rptr_idx]; // latch command

          // ---------------- WRITE OP (MODE=2'b11) ----------------
          if (DI_local[31:30] == 2'b11) begin
            for (k = 0; k < WR_Dly; k = k + 1) @(posedge CLKin);
            array_mem[DI_local[29:25]][DI_local[24:20]] = (DI_local[7:0] > 8'h7F);
            ip_rptr_idx  <= ip_rptr_idx_next;
            ip_rptr_wrap <= ip_rptr_wrap_next;
            in_process   <= 1'b0;
          end

          // ---------------- READ OP (MODE=2'b01) -----------------
          else if (DI_local[31:30] == 2'b01) begin
            if (op_full) begin
              in_process <= 1'b0;
            end else begin
              for (m = 0; m < RD_Dly; m = m + 1) @(posedge CLKin);
              DO_local = {31'b0, array_mem[DI_local[29:25]][DI_local[24:20]]};
              op_fifo[op_wptr_idx] <= DO_local;
              op_wptr_idx  <= op_wptr_idx_next;
              op_wptr_wrap <= op_wptr_wrap_next;
              ip_rptr_idx  <= ip_rptr_idx_next;
              ip_rptr_wrap <= ip_rptr_wrap_next;
              in_process   <= 1'b0;
            end
          end
					
          // ---------------- COMPUTE OP (MODE=2'b10) ----------------- 

          else if (DI_local[31:30] == 2'b10) begin
            // Sequential checks: first IP FIFO, then OP FIFO
            if (!ip_full) begin
              // IP FIFO not full → wait
              in_process <= 1'b0;
            end else begin
              // IP FIFO full AND OP FIFO has enough space → start compute
              // --- Stage 1: Load 32 rows into compute FIFO ---

							for (y = 0; y < 4; y = y + 1) begin  // To produce 4 clk cycle Delay
							  @(posedge CLKin);
							end

						  temp_ip_rptr_idx  = ip_rptr_idx;
              temp_ip_rptr_wrap = ip_rptr_wrap;

              for (x = 0; x < 32; x = x + 1) begin
                compute_fifo[ip_fifo[temp_ip_rptr_idx][29:25]] = ip_fifo[temp_ip_rptr_idx][7:0];
                temp_data = ip_fifo[temp_ip_rptr_idx][7:0]; // optional for observation

                // Manually increment temp_ip_rptr_idx with wrap
                if (temp_ip_rptr_idx == 5'd31) begin
                  temp_ip_rptr_idx = 5'd0;
                  temp_ip_rptr_wrap = ~temp_ip_rptr_wrap;
                end else begin
                  temp_ip_rptr_idx = temp_ip_rptr_idx + 1;
                end
              end

							ip_rptr_idx  = temp_ip_rptr_idx;
              ip_rptr_wrap = temp_ip_rptr_wrap;
							
							for (y = 0; y < 4; y = y + 1) begin  // To produce 4 clk cycle Delay
							  @(posedge CLKin);
							end
							
							temp_compute_rptr_idx  = compute_rptr_idx;
              temp_compute_rptr_wrap = compute_rptr_wrap;
              temp_op_wptr_idx       = op_wptr_idx;
              temp_op_wptr_wrap      = op_wptr_wrap;

              // --- Stage 2 & 3: Compute dot product and write to OP FIFO ---
              for (col = 0; col < 32; col = col + 1) begin
                temp_comp_data = 16'd0; // Reset accumulator
							
							  local_compute_rptr_idx = temp_compute_rptr_idx;
							  local_compute_rptr_wrap = temp_compute_rptr_wrap;
							
                for (row = 0; row < 32; row = row + 1) begin
                  temp_comp_data = temp_comp_data + (compute_fifo[local_compute_rptr_idx] * array_mem[row][col]);

                  // Increment local read pointer
                  if (local_compute_rptr_idx == 5'd31) begin
                    local_compute_rptr_idx = 5'd0;
                    local_compute_rptr_wrap = ~local_compute_rptr_wrap;
                  end else begin
                    local_compute_rptr_idx = local_compute_rptr_idx + 1;
                  end
                end

                // Pack and write result to OP FIFO
                DO_local = {7'd0, col[4:0], 4'd0, temp_comp_data};
                op_fifo[temp_op_wptr_idx] = DO_local;
							
							  // Increment OP FIFO write pointer
                if (temp_op_wptr_idx == 5'd31) begin
                  temp_op_wptr_idx = 5'd0;
                  temp_op_wptr_wrap = ~temp_op_wptr_wrap;
                end else begin
                  temp_op_wptr_idx = temp_op_wptr_idx + 1;
                end
              end
					
						  // Update real read and write pointers after batch compute
              compute_rptr_idx  = local_compute_rptr_idx;
              compute_rptr_wrap = local_compute_rptr_wrap;
              op_wptr_idx       = temp_op_wptr_idx;
              op_wptr_wrap      = temp_op_wptr_wrap;
							
							// For iteration this block is Used (Start)
							//if(P > 0) begin
                for (q = 0; q < P; q = q + 1) begin
								
								  for (y = 0; y < 2; y = y + 1) begin  // To produce 2 clk cycle Delay (Optional)
							      @(posedge CLKin);
							    end
								
								  temp_op_rptr_idx  = op_rptr_idx;
                  temp_op_rptr_wrap = op_rptr_wrap;
								
								  for (x = 0; x < 32; x = x + 1) begin
                    compute_fifo[op_fifo[temp_op_rptr_idx][24:20]] = op_fifo[temp_op_rptr_idx][7:0];
										
										// Manually increment temp_ip_rptr_idx with wrap
                    if (temp_op_rptr_idx == 5'd31) begin
                      temp_op_rptr_idx = 5'd0;
                      temp_op_rptr_wrap = ~temp_op_rptr_wrap;
                    end else begin
                      temp_op_rptr_idx = temp_op_rptr_idx + 1;
                    end
								  end
									
									op_rptr_idx  = temp_op_rptr_idx;
                  op_rptr_wrap = temp_op_rptr_wrap;
									
									for (y = 0; y < 4; y = y + 1) begin  // To produce 4 clk cycle Delay
							      @(posedge CLKin);
							    end
									
									temp_compute_rptr_idx  = compute_rptr_idx;
                  temp_compute_rptr_wrap = compute_rptr_wrap;
                  temp_op_wptr_idx       = op_wptr_idx;
                  temp_op_wptr_wrap      = op_wptr_wrap;
									
									for (col = 0; col < 32; col = col + 1) begin
                    temp_comp_data = 16'd0; // Reset accumulator
								    
							      local_compute_rptr_idx = temp_compute_rptr_idx;
							      local_compute_rptr_wrap = temp_compute_rptr_wrap;
							
                    for (row = 0; row < 32; row = row + 1) begin
                      temp_comp_data = temp_comp_data + (compute_fifo[local_compute_rptr_idx] * array_mem[row][col]);
								    
                      // Increment local read pointer
                      if (local_compute_rptr_idx == 5'd31) begin
                        local_compute_rptr_idx = 5'd0;
                        local_compute_rptr_wrap = ~local_compute_rptr_wrap;
                      end else begin
                        local_compute_rptr_idx = local_compute_rptr_idx + 1;
                      end
                    end

                    // Pack and write result to OP FIFO
                    DO_local = {7'd0, col[4:0], 4'd0, temp_comp_data};
                    op_fifo[temp_op_wptr_idx] = DO_local;
								    
							      // Increment OP FIFO write pointer
                    if (temp_op_wptr_idx == 5'd31) begin
                      temp_op_wptr_idx = 5'd0;
                      temp_op_wptr_wrap = ~temp_op_wptr_wrap;
                    end else begin
                      temp_op_wptr_idx = temp_op_wptr_idx + 1;
                    end
                  end
									
									// Update real read and write pointers after batch compute
                  compute_rptr_idx  = local_compute_rptr_idx;
                  compute_rptr_wrap = local_compute_rptr_wrap;
                  op_wptr_idx       = temp_op_wptr_idx;
                  op_wptr_wrap      = temp_op_wptr_wrap;
							
                end
              //end
							// For iteration this block is Used (End)

              // Done with compute batch
              in_process <= 1'b0;
					
						  //@(posedge CLKin);
            end
          end


          // --------------- UNKNOWN OPCODE: drop it ----------------
          else begin
            ip_rptr_idx  <= ip_rptr_idx_next;
            ip_rptr_wrap <= ip_rptr_wrap_next;
            in_process   <= 1'b0;
          end
        end
      end
    end
  end

  // ---------------------------------------------------------------------------
  // Init memory to 0 (sim-only convenience)
  // ---------------------------------------------------------------------------
  initial begin
    for (r = 0; r < 32; r = r + 1) begin
      for (c = 0; c < 32; c = c + 1) begin
        array_mem[r][c] = 8'h00;
      end
    end
  end

endmodule
