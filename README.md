# wasmjail

A tiny capability-restricted virtual machine for Watt, a small bytecode dialect used in this lab.

`python -m wasmjail inspect --module fixtures/modules/ok-add.watt` already assembles a module and prints the IR. `run` is still a stub: it has to instantiate memory, honour fuel and stack limits, apply the start function, and mediate host imports through the caller's preopens.

Standard library only. No Docker, no wasmtime, no third-party WebAssembly runtimes.
