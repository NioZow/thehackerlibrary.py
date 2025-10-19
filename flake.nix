{
  description = "TheHackerLibrary SDK flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
        name = "thehackerlibrary.py";
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            python.pkgs.pytest
            pkgs.uv
            pkgs.geckodriver
            pkgs.postgresql_17_jit
          ];

          name = name;
          shellHook = ''
            export name="${name}"

            if [ -f .venv/bin/activate ]; then
              source .venv/bin/activate
            else
              uv venv
              uv pip install -e .
              uv pip install -e ".[dev]"
            fi

            export PATH="$(pwd)/bin:$PATH"
          '';
        };
      }
    );
}
