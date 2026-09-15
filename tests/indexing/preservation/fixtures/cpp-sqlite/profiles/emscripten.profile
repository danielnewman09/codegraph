# Conan profile for Emscripten/WebAssembly builds
# Usage: conan install . --profile:host profiles/emscripten.profile --build=missing
#
# This profile uses the emsdk Conan package to provide the Emscripten toolchain.
# No manual emsdk installation required - Conan handles it automatically.
#
# See: https://docs.conan.io/2/examples/cross_build/emscripten.html

[settings]
os=Emscripten
arch=wasm
compiler=emcc
compiler.version=4.0.22
compiler.libcxx=libc++
compiler.cppstd=20
build_type=Release

[tool_requires]
# Emscripten SDK - built from source for SDL3 support (requires 4.0+)
emsdk/4.0.22

[conf]
# Use Unix Makefiles - Ninja may not be available in all environments
tools.cmake.cmaketoolchain:generator=Unix Makefiles
# Memory configuration for WebAssembly
tools.build:exelinkflags=["-sALLOW_MEMORY_GROWTH=1", "-sMAXIMUM_MEMORY=536870912", "-sINITIAL_MEMORY=134217728"]
tools.build:sharedlinkflags=["-sALLOW_MEMORY_GROWTH=1", "-sMAXIMUM_MEMORY=536870912", "-sINITIAL_MEMORY=134217728"]
