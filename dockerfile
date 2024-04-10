FROM python:3-alpine

ENV PYTHONIOENCODING utf-8
WORKDIR /app

RUN apk add --update \
        wget \
    # Add chromium and dependences
        udev \
        ttf-freefont \
        chromium \
        chromium-chromedriver \
    # Add Japanese font
    && mkdir noto \
    && wget -P /app/noto https://noto-website.storage.googleapis.com/pkgs/NotoSansCJKjp-hinted.zip \
    && unzip /app/noto/NotoSansCJKjp-hinted.zip -d /app/noto \
    && mkdir -p /usr/share/fonts/noto \
    && cp /app/noto/*.otf /usr/share/fonts/noto \
    && chmod 644 -R /usr/share/fonts/noto/ \
    && fc-cache -fv \
    && rm -rf /app/noto 

# Install UV
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh 
RUN /install.sh && rm /install.sh

# Install dependencies with UV
COPY requirements.txt .
RUN /root/.cargo/bin/uv pip install --system --no-cache -r requirements.txt 

COPY main.py .
CMD ["python", "main.py"]