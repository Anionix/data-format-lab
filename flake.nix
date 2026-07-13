{
  description = "Reproducible environment for Data Format Lab";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python312
              uv
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
            };
          };
        });
    };
}
