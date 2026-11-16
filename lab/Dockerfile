FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 file binutils \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pymysql
WORKDIR /work
CMD ["sleep", "infinity"]
