{
  description = "Reproducible environment for Data Format Lab";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay.url = "github:oxalica/rust-overlay";
  };

  outputs = { nixpkgs, rust-overlay, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ rust-overlay.overlays.default ];
          };
          rustToolchain = pkgs.rust-bin.nightly."2026-07-15".default.override {
            extensions = [ "rust-src" ];
          };
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python312
              uv
              ruff
              pyright
              ty
              rustToolchain
              cargo-fuzz
              duckdb
              cmake
              ninja
              clang
              protobuf
              flatbuffers
              pkg-config
              zstd
              bison
              double-conversion
              flex
              gflags
              glog
              gtest
              icu
              folly
              abseil-cpp
              fmt
              libevent
              libsodium
              lz4
              openssl
              simdjson
              snappy
              xz
              xxhash
              zlib
            ];
            env = {
              PYTHONNOUSERSITE = "1";
              UV_PYTHON = "${pkgs.python312}/bin/python3.12";
              UV_NO_EDITABLE = "1";
            } // pkgs.lib.optionalAttrs pkgs.stdenv.isLinux {
              LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
            };
          };
        });
    };
}
