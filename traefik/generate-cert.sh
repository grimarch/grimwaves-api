#!/bin/bash

mkdir -p config/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout config/certs/local-key.pem \
    -out config/certs/local-cert.pem \
    -subj "/CN=api.grimwaves.local" \
    -addext "subjectAltName=DNS:api.grimwaves.local,DNS:grimwaves.local,DNS:*.grimwaves.local"
