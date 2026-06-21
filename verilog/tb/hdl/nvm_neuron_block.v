module nvm_neuron_block(
  input               clk,
  input               rst,
  input signed [15:0] stimuli,
  input        [15:0] connection,
  input               picture_done,
  input               enable,
  output      [15:0] spike_o
);

  parameter NUM_OF_MACRO = 16;

  reg signed [15:0] THRESHOLD;
  parameter [3:0] LEAK_SHIFT = 4'd4;

  reg signed [15:0] potential [NUM_OF_MACRO-1:0];
  reg        [15:0] spike_latched;

  integer max_potential_seen;

  assign spike_o = spike_latched;

  initial begin
    THRESHOLD = 16'sd127;
    max_potential_seen = 0;

    $display("=================================");
    $display("NEURON BLOCK INITIALIZED");
    $display("THRESHOLD = %0d", THRESHOLD);
    $display("LEAK_SHIFT = %0d", LEAK_SHIFT);
    $display("=================================");
  end

  genvar i;
  generate
    for (i=0; i<NUM_OF_MACRO; i=i+1) begin : neuron_gen

      always @(posedge clk or posedge rst) begin

        if (rst) begin
          potential[i] <= 16'sd0;
          spike_latched[i] <= 1'b0;

          if (i == 0)
            max_potential_seen <= 0;
        end

        else if (picture_done) begin

          if (i == 0) begin
            $display(
              "PICTURE_DONE max_potential_seen=%0d",
              max_potential_seen
            );

            $display(
              "PICTURE_DONE spike_o=%h",
              spike_latched
            );

            max_potential_seen <= 0;
          end

          potential[i] <= 16'sd0;
          spike_latched[i] <= 1'b0;
        end

        else begin

          //--------------------------------------------------
          // Integrate + Leak
          //--------------------------------------------------
          if (enable && connection[i]) begin

            if (i == 0) begin
              $display(
                "N0 UPDATE old=%0d stim=%0d new=%0d",
                potential[i],
                stimuli,
                potential[i]
                  - (potential[i] >>> LEAK_SHIFT)
                  + stimuli
              );
            end

            potential[i] <= potential[i]
                          - (potential[i] >>> LEAK_SHIFT)
                          + stimuli;

          end
          else begin

            potential[i] <= potential[i]
                          - (potential[i] >>> LEAK_SHIFT);

          end

          //--------------------------------------------------
          // Track maximum membrane potential seen
          //--------------------------------------------------
          if ((i == 0) && (potential[i] > max_potential_seen))
            max_potential_seen <= potential[i];

          //--------------------------------------------------
          // Spike detection
          //--------------------------------------------------
          if ($signed(potential[i]) >= THRESHOLD) begin

            if (!spike_latched[i]) begin
              $display(
                "SPIKE neuron=%0d potential=%0d threshold=%0d time=%0t",
                i,
                potential[i],
                THRESHOLD,
                $time
              );
            end

            spike_latched[i] <= 1'b1;
            potential[i] <= 16'sd0;
          end

        end

      end

    end
  endgenerate

endmodule