FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATA_ROOT=/home/appuser/.trading_bot

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY requirements.txt /app/requirements.txt
COPY scripts/build_secure_kiteconnect_wheel.py /app/scripts/build_secure_kiteconnect_wheel.py
COPY scripts/install_tradebot_dependencies.py /app/scripts/install_tradebot_dependencies.py
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python /app/scripts/install_tradebot_dependencies.py --repo-root /app

COPY . /app
RUN pip install --no-cache-dir -e . \
    && chown -R appuser:appuser /app /home/appuser

USER appuser

CMD ["pytest", "-q"]
