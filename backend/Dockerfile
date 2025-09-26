# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

# ARG PYTHON_VERSION=3.11
# FROM python:${PYTHON_VERSION} as base

# # Prevents Python from writing pyc files.
# ENV PYTHONDONTWRITEBYTECODE=1

# # Keeps Python from buffering stdout and stderr to avoid situations where
# # the application crashes without emitting any logs due to buffering.
# ENV PYTHONUNBUFFERED=1

# WORKDIR /app

# # Download dependencies as a separate step to take advantage of Docker's caching.
# # Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# # Leverage a bind mount to requirements.txt to avoid having to copy them into
# # into this layer.
# RUN --mount=type=cache,target=/root/.cache/pip \
#     --mount=type=bind,source=requirements.txt,target=requirements.txt \
#     python -m pip install -r requirements.txt

# # Switch to the non-privileged user to run the application.
# USER appuser

# # Copy the source code into the container.
# COPY . .

# # Expose the port that the application listens on.
# EXPOSE 8000

# # Run the application.
# CMD uvicorn main:app --reload --port 8000 --host 0.0.0.0

# syntax=docker/dockerfile:1

# Set Python version
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    libjpeg-dev \
    zlib1g-dev \
    libmupdf-dev \
    libfreetype6-dev \
    libffi-dev \
    libblas-dev \
    liblapack-dev \
    gfortran \
    libopenblas-dev \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies (with pip cache mount for speed)
# RUN --mount=type=cache,target=/root/.cache/pip \
#     python -m pip install --upgrade pip \
#     && python -m pip install --prefer-binary -r requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --prefer-binary -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create non-root user
RUN useradd -m appuser
USER appuser

# Expose port
EXPOSE 8080

# Run the app
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]