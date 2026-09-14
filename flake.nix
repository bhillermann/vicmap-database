{
  description = "Vicmap -> PostGIS refresh (get updates from automations@vegetationlink.com.au)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    opnix.url = "github:brizzbuzz/opnix";
  };

  outputs = inputs@{ flake-parts, opnix, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];

      perSystem = { pkgs, lib, ... }:

      let
        
        buildOpnix = opnix.packages.${pkgs.stdenv.hostPlatform.system}.default;

        opnixEnvConfig = {
          format = "shell";
          vars = [
            { name = "O365_AUTH_ID";     reference = "op://nixos-services/o365_app_credentials/username"; }
            { name = "O365_AUTH_SECRET"; reference = "op://nixos-services/o365_app_credentials/password"; }
            { name = "TENANT_ID";        reference = "op://nixos-services/o365_app_credentials/tenant_id"; }
          ];
        };

        python-o365 = pkgs.python3Packages.buildPythonPackage rec {
          pname = "O365";
          version = "2.1";

          src = pkgs.fetchFromGitHub {
            owner = "O365";
            repo = "python-o365";
            rev = "v${version}";
            sha256 = "sha256-2sXNklHSwYlKuGd7HeM5AGZooBV0qWZ5pRC/WAZLY2M=";
          };

          pyproject = true;
          build-system = with pkgs.python3Packages; [ setuptools ];

          propagatedBuildInputs = with pkgs.python3Packages; [
            requests
            requests-oauthlib
            msal
            tzlocal
            tzdata
            beautifulsoup4
            python-dateutil
          ];

          doCheck = false;
        };

        in {

        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            git
            buildOpnix
            (python3.withPackages (ps: [ python-o365 ps.html5lib ]))
          ];

        shellHook = ''
          echo "Entering development environment for vicmap-database"
          if [ -z "''${OPNIX_ENV_DISABLE:-}" ]; then
          eval "$(opnix env \
            -config-json ${lib.escapeShellArg (builtins.toJSON opnixEnvConfig)} \
            -token-file "''${OPNIX_ENV_TOKEN_FILE:-$HOME/.config/opnix/token}")"
          fi        '';

       };
      };
    };
}
