FROM python:3.12-alpine
WORKDIR /app
COPY shared /app/shared
COPY services/payment-service/server.py /app/server.py
ARG GIT_SHA=local
ENV GIT_SHA=${GIT_SHA}
ENV PYTHONPATH=/app
ENV PORT=8080
EXPOSE 8080
CMD ["python", "/app/server.py"]
