# Use an official Python runtime as a parent image
FROM python:3.12-slim
# Set the working directory in the container to /app
WORKDIR /app

# Add the current directory contents into the container at /app
ADD . /app

# Install Firefox and necessary dependencies
RUN apt-get update && \
    apt-get install -y firefox-esr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Geckodriver
RUN apt-get update && \
    apt-get install -y wget && \
    wget https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz && \
    tar -xzf geckodriver-v0.34.0-linux64.tar.gz -C /usr/local/bin && \
    rm geckodriver-v0.34.0-linux64.tar.gz && \
    apt-get remove -y wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in depends.txt
RUN pip install -r depends.txt

# Run main.py when the container launches
CMD ["python", "main.py"]