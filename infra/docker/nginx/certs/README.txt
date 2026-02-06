Place TLS certificate files here for HTTPS (ecomcore.ru):
  fullchain.pem   -> certificate + chain
  privkey.pem     -> private key

Without these files nginx will not start (ssl_certificate/ssl_certificate_key).
If using Let's Encrypt on the host, you can mount that path instead in docker-compose:
  - /etc/letsencrypt/live/ecomcore.ru:/etc/nginx/ssl:ro
