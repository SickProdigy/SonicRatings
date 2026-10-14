# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Install the same package and command used by native runs
RUN pip install --no-cache-dir .

# Use an entrypoint script
ENTRYPOINT ["sonicratings"]
