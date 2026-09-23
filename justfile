module_name := "pgiscluster"

# list commands
default:
  @just --list

# install the packages
install:
  {{ if path_exists("uv.lock") == "true" { "uv sync --all-groups --all-extras --locked --inexact" } else { "uv sync --all-groups --all-extras --inexact" } }}

# setup for development
setup: install git-setup

# run test coverage and create
test-cov:
  uv run pytest --cov=src/pgiscluster --cov-report=lcov:lcov.info --cov-report=term-missing --cov-report html --cov-report xml

# update packages and uv lock file
update:
  uv sync -U --all-groups --all-extras --inexact

# set up pre-commit hooks
git-setup:
  @[ -d .git ] || git init
  uv run prek install
