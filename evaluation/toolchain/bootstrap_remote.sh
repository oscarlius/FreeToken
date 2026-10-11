#!/usr/bin/env bash
# Creates only toolchain-owned virtual environments.  It never mutates the
# FreeToken runtime venv or starts a model service.
set -euo pipefail

toolchain_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
python_bin=${PYTHON_BIN:-python3}
locked=false
if [[ ${1:-} == "--locked" ]]; then
  locked=true
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--locked]" >&2
  exit 2
fi

# The host exports a socks5 proxy but its bootstrapped pip lacks PySocks,
# creating a circular install failure.  PyPI is directly reachable from this
# host, so remove proxy variables only for these package-manager subprocesses.
run_pip() {
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY "$@"
}

create_env() {
  local env_name=$1
  local requirements=$2
  local env_path="$toolchain_dir/$env_name"
  local install_file="$toolchain_dir/$requirements"
  local freeze_file="$toolchain_dir/${env_name}.freeze.txt"
  local current_freeze
  if "$locked"; then
    install_file="$freeze_file"
    [[ -f "$install_file" ]] || { echo "missing lock receipt: $install_file" >&2; exit 2; }
  fi
  "$python_bin" -m venv "$env_path"
  if ! "$locked"; then
    run_pip "$env_path/bin/python" -m pip install --upgrade pip
  fi
  run_pip "$env_path/bin/python" -m pip install --requirement "$install_file"
  "$env_path/bin/python" -m pip check
  current_freeze=$(mktemp "$toolchain_dir/.${env_name}.freeze.XXXXXX")
  "$env_path/bin/python" -m pip freeze --all | LC_ALL=C sort > "$current_freeze"
  if "$locked"; then
    if ! cmp -s "$freeze_file" "$current_freeze"; then
      diff -u "$freeze_file" "$current_freeze" >&2 || true
      rm -f "$current_freeze"
      echo "locked environment differs from $freeze_file" >&2
      return 1
    fi
    rm -f "$current_freeze"
  else
    mv "$current_freeze" "$freeze_file"
  fi
}

create_env venv-aiperf requirements-aiperf.txt
create_env venv-eval requirements-eval.txt
