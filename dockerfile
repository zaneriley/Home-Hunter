FROM python:alpine as builder

ENV PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies 
RUN apk add --no-cache \
        wget \
        udev \
        ttf-freefont \
        chromium \
        chromium-chromedriver \
    # Add Japanese font for screenshots
    && mkdir noto \
    && wget -P /app/noto https://noto-website.storage.googleapis.com/pkgs/NotoSansCJKjp-hinted.zip \
    && unzip /app/noto/NotoSansCJKjp-hinted.zip -d /app/noto \
    && mkdir -p /usr/share/fonts/noto \
    && cp /app/noto/*.otf /usr/share/fonts/noto \

# Install UV
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh 
RUN /install.sh && rm /install.sh

# Install dependencies with UV
COPY requirements.txt .
RUN /root/.cargo/bin/uv pip install --system --no-cache -r requirements.txt 

# Copy only the necessary files
COPY main.py .


# Create a non-root user and switch to it
RUN adduser -D python \
    && chown -R python:python /app ../usr/share/fonts

USER python

CMD ["python", "main.py"]