FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp

RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" \
    "pandas>=2.2,<3.0" \
    "numpy>=1.26,<2.2" \
    "scikit-learn>=1.5,<2.0" \
    "matplotlib>=3.9,<4.0"

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /work \
    && chown 1000:1000 /work

WORKDIR /work
USER 1000:1000

CMD ["python", "-c", "print('sandbox ready')"]
