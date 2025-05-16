FROM hashicorp/vault:1.19.2

RUN apk add --no-cache curl jq

RUN mkdir -p /vault-agent/templates /vault-agent/rendered /vault-agent/sockets /vault-agent/auth /vault-agent/token
COPY config/agent.hcl /vault-agent/config/agent.hcl

ENTRYPOINT ["vault", "agent", "-config=/vault-agent/config/agent.hcl"]
