clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_poll_in.cpp -o deep_targets/target_poll_in
clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_poll_out.cpp -o deep_targets/target_poll_out
clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_isr.cpp -o deep_targets/target_isr
clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_set_baudrate.cpp -o deep_targets/target_set_baudrate
clang++ -g -fsanitize=fuzzer,address -Iharnesses/include deep_targets/fuzz_pl011_fifo_fill.cpp -o deep_targets/target_fifo_fill
