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
            # D-58/T-03-03: the vicmap_loader role's PostgreSQL password. Only an op://
            # reference lives here; the value comes from 1Password through opnix exactly
            # as O365_AUTH_SECRET does above. Never read from vicmap.toml, never appears
            # in argv. Operator must create this item (03-01-PLAN.md user_setup) --
            # see 03-01-USER-SETUP.md.
            { name = "VICMAP_DB_PASSWORD"; reference = "op://nixos-services/vicmap_loader_credentials/password"; }
            # D-74: the vicmap_reader role's own PostgreSQL password, sourced from
            # 1Password through opnix exactly as VICMAP_DB_PASSWORD above -- never
            # from vicmap.toml, never in argv. Operator must create this item
            # (04-02-PLAN.md user_setup) before the reader-login verification
            # (04-05) can run.
            { name = "VICMAP_READER_PASSWORD"; reference = "op://nixos-services/vicmap_reader_credentials/password"; }
          ];
        };

        # D-50 correction (03-RESEARCH.md Common Pitfall 1): the named `proj-data`
        # package does not exist at this flake's pinned nixpkgs revision -- `proj`,
        # `proj-datumgrid`, and `proj_7` are the only `proj*` matches, and PROJ >= 7
        # ships zero grid files in `share/proj`. 03-01's Task 2 checkpoint selected
        # option A (vendor-fetchurl): vendor the one ICSM NTv2 grid PROJ needs for the
        # GDA94 VicGrid -> GDA2020 VicGrid transform (D-51's OGR_CT_ONLY_BEST=YES /
        # OGR_CT_ALLOW_BALLPARK=NO otherwise hard-stops the first mixed-CRS load), the
        # same way python-o365 below is vendored by pinned hash. No PROJ_NETWORK, no
        # runtime outbound host (T-03-04).
        icsmGda94Gda2020Grid = pkgs.fetchurl {
          url = "https://cdn.proj.org/au_icsm_GDA94_GDA2020_conformal_and_distortion.tif";
          sha256 = "89bb9e5c55a714c8925ddc134bf4c191be8df2607b229a05efb778f5f6166ee0";
        };

        # Research Open Question 2, settled empirically in 03-01 Task 3: PROJ 9.8.1 /
        # pyproj 3.7.2 do NOT search a colon-joined PROJ_DATA list for grids -- a
        # colon-joined "${pkgs.proj}/share/proj:<grid dir>" left the vendored grid
        # reported unavailable (pyproj.datadir.get_data_dir() only ever reads the
        # first entry). Only a single merged directory containing both proj.db and
        # the grid resolves it. `pkgs.fetchurl`'s output is also the grid file
        # *itself* at a hash-prefixed store path, whose basename is not the plain
        # ICSM filename PROJ searches for, so it must be symlinked under its real
        # name inside that merged directory.
        projDataDir = pkgs.runCommand "proj-data-with-icsm-grid" { } ''
          mkdir -p "$out"
          for f in ${pkgs.proj}/share/proj/*; do
            ln -s "$f" "$out/$(basename "$f")"
          done
          ln -s ${icsmGda94Gda2020Grid} "$out/au_icsm_GDA94_GDA2020_conformal_and_distortion.tif"
        '';

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
            gdal  # provides the ogrinfo/ogr2ogr CLI tools -- python3Packages.pyogrio
                  # does not propagate them (its propagatedBuildInputs are only
                  # certifi, numpy, packaging, python3), so ogrinfo needs this
                  # separate flake dependency to resolve inside `nix develop`.
            postgresql  # supplies the psql client that runs D-60's operator-run
                        # db/provision_vicmap_loader.sql from inside the dev shell,
                        # so provisioning does not depend on the operator's ambient
                        # profile.
            (python3.withPackages (ps: [
              python-o365
              ps.html5lib
              # Reviewed supply-chain evidence (02-RESEARCH.md Package Legitimacy
              # Audit): both flagged [SUS] by the automated PyPI metadata lookup
              # (unknown-downloads/too-new/no-repository), assessed as lookup
              # artifacts rather than slopsquat signals, and the operator waived
              # the checkpoint:human-verify during Phase 2 planning (see
              # 02-01-PLAN.md's "Package legitimacy - operator waiver" note).
              ps.pyogrio  # https://github.com/geopandas/pyogrio
              ps.pyproj   # https://github.com/pyproj4/pyproj
              # Reviewed supply-chain evidence (03-RESEARCH.md Package Legitimacy
              # Audit): flagged [SUS] on too-new (most recent point release dated
              # 2026-09-18) and unknown-downloads; the audit seam also returned the
              # project homepage https://psycopg.org/ rather than a repository URL.
              # Source repository: https://github.com/psycopg/psycopg. Unlike the
              # pyogrio/pyproj pair above, this one was NOT waived at planning time --
              # the operator cleared it at 03-01-PLAN.md's Task 1 blocking-human gate
              # (approved 2026-09-21) after confirming the PyPI project, the
              # psycopg/psycopg source repository, and the nixpkgs-curated 3.3.4
              # version.
              ps.psycopg  # https://github.com/psycopg/psycopg
            ]))
          ];

        shellHook = ''
          echo "Entering development environment for vicmap-database"
          if [ -z "''${OPNIX_ENV_DISABLE:-}" ]; then
          eval "$(opnix env \
            -config-json ${lib.escapeShellArg (builtins.toJSON opnixEnvConfig)} \
            -token-file "''${OPNIX_ENV_TOKEN_FILE:-$HOME/.config/opnix/token}")"
          fi
          # D-50 correction / T-03-01, T-03-02: point PROJ_DATA at the single merged
          # directory (see projDataDir above) holding both proj.db and the vendored
          # ICSM GDA94<->GDA2020 grid, so the GDA94 VicGrid -> GDA2020 VicGrid
          # transform has an available best operation instead of D-51 hard-stopping
          # every mixed-CRS load.
          export PROJ_DATA="${projDataDir}"
        '';

       };
      };
    };
}
