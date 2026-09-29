# The LP64 port (`ninja linux64`)

`ninja linux64` builds the game as a true 64-bit x86-64 (LP64) executable,
`build/linux64/halo`. Pointers and `long` are 64 bits. This is experimental
and unfinished.

Current state: the game starts, initialises OpenGL, audio and networking,
finds the maps folder, reads the cache file headers, loads the tag blob of
the `ui` map, and translates its header and instance table. It then runs
stably, but cannot interpret the tags' own structures yet (see "The data
translation layer" below), so no menu appears. Known lesser defect: player
profile saves fail (`file_write` reports success with nothing written).

## What has been ported

- The cache file headers (three file-scope copies of `struct
  cache_file_header`, in cache_files.c, cache_files_windows.c and
  cache_files_decompress_windows.c) are explicit 32-bit layouts
  (`long32`/`ulong32`, cseries.h), read raw from disk as before. A drifting
  copy was what made every map "not found", and its oversized memset then
  trampled the sound cache globals.
- The XDK/Win32 surface (`port/include/xdk`): as on Win64, the Win32
  integers (`DWORD`, `LONG`, `ULONG`, `HRESULT`, and the fields and
  prototypes spelled `long`) are 32-bit through the `HALO_LONG32`/
  `HALO_ULONG32` macros (halo_linux_prefix.h); only the pointer-sized
  family (`DWORD_PTR`, `ULONG_PTR`, `SIZE_T`, handles) is 64-bit. `u_long`
  keeps glibc's spelling (its typedef collides with the SDK's otherwise);
  the winsock structure fields that must stay 32-bit are pinned directly.
- The tag blob's header and instance table
  (`tag_cache_translate_header_and_instances_64` in cache_files.c). The
  blob's pointers are the absolute addresses it is loaded at — the port
  reserves the Xbox memory map below 4 GB, so they zero-extend to valid
  LP64 pointers; only the struct layouts differ.
- `pal_tags_loaded` is disabled on LP64: it edits tag structures, which
  still have their disk layouts.

## Why LP64 is not a build flag

The decompilation was written against the Xbox/MSVC Win32 environment. On
LP64 two kinds of code drift:

1. **`long` becomes 64-bit.** Benign in most of the engine — MSVC code uses
   `long` as the pointer-sized integer, which it is again on LP64 — but every
   structure whose layout is fixed by a file format (tags, cache files,
   saved games) or by the network protocol changes size.
2. **Pointers in structures become 8 bytes.** The map files on disk contain
   tag structures with 4-byte pointers (relocated at load with the cache
   "magic"). On LP64 the in-memory layout no longer matches the disk layout,
   anywhere a tag structure holds a pointer (`struct tag_block`,
   `struct tag_reference`, `struct tag_data`, and most tag groups).

## What the build does differently

`tools/linux_build.py` has a target list, `LINUX_TARGETS`:

- `linux`: 32-bit, as shipped. `-malign-double` and `-freg-struct-return`
  reproduce the MSVC ABI.
- `linux64`: LP64. x86-64 already aligns 64-bit members to 8 bytes and
  returns small aggregates in registers, so neither flag applies (and clang
  rejects them for this target). There is no optimisation profile for it
  yet; `pgo/halo_linux.profdata` belongs to the 32-bit build.

The prefix header (`port/linux/include/halo_linux_prefix.h`) defines
`HALO_LINUX64` on x86-64, next to the existing `HALO_LINUX`.

## The layout asserts

The decompilation guards the Xbox layouts with compile-time asserts,
`typedef char name[expr ? 1 : -1]`. They are the exact, machine-checked list
of every structure whose layout the port must care about. On LP64 each of
them that involves a pointer or a `long` fails, so the prefix header routes
them through `HALO_LAYOUT_ASSERT_32(expr)`: unchanged on the 32-bit build,
a harmless typedef on LP64. **Every assert that fails under LP64 is a work
item for the data translation layer.** To get the list back, make
`HALO_LAYOUT_ASSERT_32` evaluate its expression again and read the errors.

## LP64 bugs found so far

- `terminal_printf` declared its `va_list` as `char *` (fine on Win32, where
  they are the same type). On LP64 `va_start` wrote a full `__va_list_tag`
  into an 8-byte variable and every `v*printf` through it read garbage.
- The crash reporter in `port/linux/src/memory_watch.c` read the 32-bit
  `ucontext` registers (`REG_EIP`, ...); it now uses `REG_RIP`/`REG_RBP`/
  `REG_RSP` on x86-64.

## The data translation layer (not implemented)

The remaining boss fight. The tags' own structures in the blob keep the
32-bit disk layout: every `struct tag_block`, `struct tag_reference` and
`struct tag_data` is smaller on disk than its LP64 form, and the group
structures (scenario, bitmaps, sounds, models, ...) mix both with pointers.

The original plan was to walk the blob with the tag field metadata
(`struct tag_block_definition`, `struct tag_field`) and expand each element
to its LP64 layout. **That metadata does not exist in this build**: the
cache-beta decompilation kept the field definitions of only a handful of
groups (the hs_* blocks, recorded animations, the leaf map), and the block
definitions that exist record `element_size` as `sizeof()` of the compiled
struct, not the file's.

So the group layouts have to be reconstructed — the community has them
complete and open (Invader's tag definitions cover every group of the
game) — and joined with the compiled LP64 layouts (both sides are in the
DWARF of the two builds: the 32-bit build's `sizeof`/`offsetof` is the file
layout, the 64-bit build's is the memory layout). A generator can emit a
layout table from the two; the runtime translator then converts each tag at
load, lazily at `tag_get` or eagerly at `scenario_tags_load`.

The same treatment is needed for the scenario's structure BSP header and for
anything else read with a raw memory "magic" delta.

Saved games (raw dumps of the game state) and the system-link protocol carry
the LP64 layouts; saves and multiplayer are therefore not compatible between
the 32-bit and 64-bit builds. That is acceptable: the formats are versioned
per build anyway.

## Trying it

```sh
python configure.py --release
ninja linux64
build/linux64/halo
```

Without game data it does what the 32-bit build does: asks for an Xbox disc
image, and without one runs its main loop with a black window (the error
dialog itself lives in the `ui` map, which is game data).
