FROM python:3.12-slim

WORKDIR /app

# Install git for setuptools_scm
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Initialize git repo for setuptools_scm (needed if .git isn't copied)
RUN git config --global --add safe.directory /app

# Install the package with dev dependencies
RUN pip install --upgrade pip && pip install .[dev]

# Default command runs all CI checks
CMD ["sh", "-c", "pytest && black --check src tests && isort --check src tests && flake8 src tests && mypy src/framer"]
