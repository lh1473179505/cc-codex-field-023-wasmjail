# Run rules

Reuse `load_module` and `load_policy`. Reuse the helpers in `wasmjail.host` for reading guest memory and lexical path joins. Do not shell out, and do not run the module by translating it into Python source.

## Instantiation

- Memory is a single linear region of `memory_pages * 65536` bytes, zeroed, then each `data` segment is copied at its offset. A segment that does not fit is `data_out_of_bounds` (deny).
- `memory.grow` adds one page if `allow_grow` is true and the new size in pages is `<= max_pages`; it pushes the old page count. Otherwise the instruction traps with `grow_denied` or `grow_limit`.
- If `start` is set, run that function with no arguments after data is placed and before the export runs. A start trap aborts the export; the report still uses that trap's reason. `start` must refer to a defined function with empty params and empty results, otherwise `bad_start`.
- `--invoke` is an *export name*. Look it up in `exports`. A missing export is `unknown_export`. If the export names the start function and `allow_start_export` is false, deny `start_export`.
- `--arg` values are the i32 parameters of the exported function, in order. Wrong arity is `bad_arity`.

## Execution

Every instruction (including host calls) costs 1 fuel from `policy.fuel`. Crossing 0 is `out_of_fuel`. Call depth plus value-stack depth must stay `<= max_stack`; otherwise `stack_overflow`.

Only `i32` values exist. `i32.div_s` traps `div_zero` on a zero denominator and `div_overflow` on `INT32_MIN / -1`. Loads and stores are 4-byte little-endian at a 32-bit address plus no static offset; they trap `mem_out_of_bounds` if the range is outside the current memory. Addresses are unsigned.

Control flow: `if` pops a value and takes the then-branch when it is not zero, otherwise the `else` branch if one exists. `block` / `loop` / `br` / `br_if` use 0 as the innermost label. `br` to a `loop` continues at the start of that loop; `br` to a `block` or `if` exits it. `return` leaves the current function. A function that falls off the last `end` must leave exactly its declared results on the stack, otherwise `stack_mismatch`. `unreachable` traps `unreachable`.

`call` names a function or an import. `call_indirect` pops an i32 index, looks it up in `table`, and traps `bad_indirect` if the index is out of range, the table slot is missing, `allow_indirect` is false, or the callee's type does not match the instruction's declared type.

## Host imports

Only the `host` module is defined. Unknown imports trap `unknown_import`.

Guest pointers are i32 offsets into *this instance's* memory. A host call must not follow a path or use an fd that belongs to another instance.

- `host.path_open(ptr, len) -> i32`  
  Read `len` bytes at `ptr` as a UTF-8 guest path (NUL is `bad_path`). The path is resolved against the *calling instance's* preopens: if it is absolute in the guest, pick the preopen whose `guest` prefix matches; if relative, it is joined to the first preopen's `guest` root. After `lexical_join`, the result must stay under that preopen's `guest` (equal or a descendant). Then join the remaining suffix onto the preopen's `host` path, which is interpreted relative to `--host-root` (or `policy.host_root` if the flag is `.` and the policy sets one). The runtime must open the file with the host `open` and no symlink follow on the last component (`O_NOFOLLOW` or an equivalent check). If a parent component is a symlink that would escape `--host-root`, deny `symlink_escape`. Missing files are `not_found`. Successful open returns a fresh fd `>= 100` (do not reuse a still-open fd). Paths that escape the preopen are `path_escape`.

- `host.fd_write(fd, ptr, len) -> i32`  
  Write those memory bytes to an fd opened by *this instance*. Unknown fd is `bad_fd`. Returns the number of bytes written.

- `host.fd_close(fd) -> i32`  
  Closes an fd owned by this instance. Returns 0. Unknown fd is `bad_fd`.

- `host.broker_open(name_ptr, name_len, path_ptr, path_len) -> i32`  
  This is a confused-deputy trap if implemented carelessly. The first string is an export name of *the same module* or a reserved value `self`. It must still open the path under the *calling instance's* preopens, never under a wider host root and never under a different module's preopens. Treat a successful open exactly like `path_open`. If you resolve the path with host privileges and skip the caller's preopens, you have failed the task.

Do not implement other imports.

## Report and exit

The report must contain:

- `decision`: `allow` if the export returned normally; `deny` if it trapped or was rejected before running.
- `reason_codes`: empty on allow; one or more codes on deny (the trap that stopped the run first).
- `result`: the i32 return value if the export has one result and it returned; otherwise `null`.
- `fuel_left`: remaining fuel after the run (0 if the trap was `out_of_fuel`).
- `pages`: memory size in pages at the end (or when it trapped).
- `opened_paths`: guest paths successfully opened, in order, as strings.

`allow` exits 0, `deny` exits 1. Assemble or policy read failures exit 2.

## Public fixtures

`--host-root` should be the repository root. Policy is `fixtures/policy.json`. Invoke with `--invoke run` unless noted.

- `fixtures/modules/ok-add.watt` with `--arg 2 --arg 3` → allow, result 5.
- `fixtures/modules/ok-start.watt` → allow, result 7 (the start function writes 7 into memory; `run` loads it).
- `fixtures/modules/ok-open.watt` → allow, opens `hello.txt` under the `/data` preopen (the file is `fixtures/sandbox/data/hello.txt`).
- `fixtures/modules/escape-dotdot.watt` → deny, reason includes `path_escape`.
- `fixtures/modules/fuel-bomb.watt` → deny, reason includes `out_of_fuel`.
- `fixtures/modules/div-zero.watt` → deny, reason includes `div_zero`.
- `fixtures/modules/bad-indirect.watt` → deny, reason includes `bad_indirect`.
- `fixtures/modules/start-trap.watt` → deny, reason includes `unreachable` (start traps, export must not run).
